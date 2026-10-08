use crate::host::{Handle, Local, Result, ok, status, wide};
use std::{
    io::Write,
    mem::zeroed,
    os::windows::fs::MetadataExt,
    path::{Path, PathBuf},
    ptr::{null, null_mut},
    time::{Duration, Instant},
};
use windows_sys::Win32::{
    Foundation::{ERROR_SHARING_VIOLATION, INVALID_HANDLE_VALUE},
    Security::{Authorization::*, *},
    Storage::FileSystem::*,
    System::SystemServices::MAXIMUM_ALLOWED,
};

struct Entry {
    handle: Handle,
    directory: bool,
}

fn open(path: &Path) -> Result<Entry> {
    // MAXIMUM_ALLOWED has documented non-propagating SetSecurityInfo semantics.
    // Each object is checked and updated through this exact, non-reparse handle.
    let name = wide(path);
    let deadline = Instant::now() + Duration::from_secs(3);
    let handle = loop {
        let raw = unsafe {
            CreateFileW(
                name.as_ptr(),
                MAXIMUM_ALLOWED,
                FILE_SHARE_READ,
                null(),
                OPEN_EXISTING,
                FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS,
                null_mut(),
            )
        };
        if raw != INVALID_HANDLE_VALUE && !raw.is_null() {
            break Handle(raw);
        }
        let error = std::io::Error::last_os_error();
        let remaining = deadline.saturating_duration_since(Instant::now());
        // A file can still be held briefly across worker restarts. Keep the
        // exclusive write/delete boundary, and validate the acquired handle
        // normally; persistent contention must still stop startup.
        if error.raw_os_error() != Some(ERROR_SHARING_VIOLATION as i32) || remaining.is_zero() {
            return Err(format!("lock sandbox path '{}': {error}", path.display()));
        }
        std::thread::sleep(remaining.min(Duration::from_millis(25)));
    };
    let mut info: BY_HANDLE_FILE_INFORMATION = unsafe { zeroed() };
    ok(
        unsafe { GetFileInformationByHandle(handle.0, &mut info) },
        "inspect sandbox path",
    )?;
    let directory = info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY != 0;
    if info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT != 0
        || (!directory && info.nNumberOfLinks != 1)
    {
        return Err(format!(
            "sandbox path cannot be a reparse point or hard link: {}",
            path.display()
        ));
    }
    Ok(Entry { handle, directory })
}

fn collect(path: &Path, entries: &mut Vec<Entry>) -> Result<()> {
    let entry = open(path)?;
    let directory = entry.directory;
    entries.push(entry); // Retain the parent lock throughout traversal and ACL updates.
    if directory {
        for child in std::fs::read_dir(path).map_err(|e| format!("read sandbox package: {e}"))? {
            collect(&child.map_err(|e| e.to_string())?.path(), entries)?;
        }
    }
    Ok(())
}

// Both ACLs belong to live descriptors returned by the Windows security APIs.
// Compare the complete lists, including order/flags; matching rights alone is
// insufficient when inherited or deny entries are present.
unsafe fn same_acl(left: *const ACL, right: *const ACL) -> bool {
    if left.is_null() || right.is_null() {
        return left == right;
    }
    unsafe {
        (*left).AclSize == (*right).AclSize
            && std::slice::from_raw_parts(left.cast::<u8>(), (*left).AclSize as usize)
                == std::slice::from_raw_parts(right.cast::<u8>(), (*right).AclSize as usize)
    }
}

fn grant(entry: &Entry, sid: PSID, rights: u32, writable: bool) -> Result<usize> {
    let (mut acl, mut descriptor) = (null_mut(), null_mut());
    status(
        unsafe {
            GetSecurityInfo(
                entry.handle.0,
                SE_FILE_OBJECT,
                DACL_SECURITY_INFORMATION,
                null_mut(),
                null_mut(),
                &mut acl,
                null_mut(),
                &mut descriptor,
            )
        },
        "read package ACL",
    )?;
    let _descriptor = Local(descriptor);
    if acl.is_null() {
        return Err("sandbox paths require an explicit access control list".into());
    }
    let access = EXPLICIT_ACCESS_W {
        grfAccessPermissions: rights,
        grfAccessMode: GRANT_ACCESS,
        grfInheritance: if entry.directory {
            CONTAINER_INHERIT_ACE | OBJECT_INHERIT_ACE
        } else {
            0
        },
        Trustee: TRUSTEE_W {
            pMultipleTrustee: null_mut(),
            MultipleTrusteeOperation: NO_MULTIPLE_TRUSTEE,
            TrusteeForm: TRUSTEE_IS_SID,
            TrusteeType: TRUSTEE_IS_UNKNOWN,
            ptstrName: sid.cast(),
        },
    };
    let mut updated = null_mut();
    status(
        unsafe { SetEntriesInAclW(1, &access, acl, &mut updated) },
        "add container ACL",
    )?;
    let _updated = Local(updated.cast());
    let mut writes = 0;
    if !unsafe { same_acl(acl, updated) } {
        status(
            unsafe {
                SetSecurityInfo(
                    entry.handle.0,
                    SE_FILE_OBJECT,
                    DACL_SECURITY_INFORMATION,
                    null_mut(),
                    null_mut(),
                    updated,
                    null(),
                )
            },
            "apply container ACL",
        )?;
        writes += 1;
    }
    if writable {
        let mut descriptor = null_mut();
        ok(
            unsafe {
                ConvertStringSecurityDescriptorToSecurityDescriptorW(
                    wide(if entry.directory {
                        "S:(ML;OICI;NW;;;LW)"
                    } else {
                        "S:(ML;;NW;;;LW)"
                    })
                    .as_ptr(),
                    1,
                    &mut descriptor,
                    null_mut(),
                )
            },
            "create state integrity label",
        )?;
        let _descriptor = Local(descriptor);
        let (mut present, mut defaulted, mut sacl) = (0, 0, null_mut());
        ok(
            unsafe {
                GetSecurityDescriptorSacl(descriptor, &mut present, &mut sacl, &mut defaulted)
            },
            "read state integrity label",
        )?;
        let (mut current, mut current_descriptor) = (null_mut(), null_mut());
        status(
            unsafe {
                GetSecurityInfo(
                    entry.handle.0,
                    SE_FILE_OBJECT,
                    LABEL_SECURITY_INFORMATION,
                    null_mut(),
                    null_mut(),
                    null_mut(),
                    &mut current,
                    &mut current_descriptor,
                )
            },
            "read state integrity label",
        )?;
        let _current_descriptor = Local(current_descriptor);
        if !unsafe { same_acl(current, sacl) } {
            status(
                unsafe {
                    SetSecurityInfo(
                        entry.handle.0,
                        SE_FILE_OBJECT,
                        LABEL_SECURITY_INFORMATION,
                        null_mut(),
                        null_mut(),
                        null(),
                        sacl,
                    )
                },
                "apply state integrity label",
            )?;
            writes += 1;
        }
    }
    Ok(writes)
}

fn cache_key(bin: &Path, node: &Path, code: &Path, sid: PSID) -> Result<String> {
    let mut key = format!(
        "Marea LPAC package ACL v2\n{}\n",
        crate::host::sid_string(sid)?
    );
    for path in [
        node.to_path_buf(),
        bin.join("marea-agent.exe"),
        code.to_path_buf(),
        code.join("worker.mjs"),
        code.join("package-lock.json"),
    ] {
        match std::fs::symlink_metadata(&path) {
            Ok(meta) => {
                if meta.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0 {
                    return Err("package cache anchors must not be links".into());
                }
                key.push_str(&format!(
                    "{}:{}:{}\n",
                    meta.file_size(),
                    meta.creation_time(),
                    meta.last_write_time()
                ));
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => key.push_str("absent\n"),
            Err(error) => return Err(error.to_string()),
        }
    }
    Ok(key)
}

fn cached(path: &Path, key: &str) -> Result<bool> {
    if !path.try_exists().map_err(|e| e.to_string())? {
        return Ok(false);
    }
    let guard = open(path)?;
    if guard.directory || std::fs::metadata(path).map_err(|e| e.to_string())?.len() > 4096 {
        return Err("invalid package permission cache".into());
    }
    Ok(std::fs::read_to_string(path).map_err(|e| e.to_string())? == key)
}

pub(super) fn cache_path(bin: &Path, validation: bool) -> PathBuf {
    bin.join(if validation {
        "marea-agent-validation-access.txt"
    } else {
        "marea-agent-access.txt"
    })
}

pub(super) fn prepare(
    bin: &Path,
    node: &Path,
    code: &Path,
    state: &Path,
    sid: PSID,
    validation: bool,
) -> Result<()> {
    let began = std::time::Instant::now();
    let tracing = std::env::var_os("MAREA_AGENT_TRACE").is_some_and(|value| value == "1");
    let mark = |stage: &str, count: usize| {
        if tracing {
            eprintln!(
                "marea-agent · {stage} ({count} paths): {} ms",
                began.elapsed().as_millis()
            );
        }
    };
    let key = cache_key(bin, node, code, sid)?;
    let cache = cache_path(bin, validation);
    let already_prepared = cached(&cache, &key)?;
    let mut readonly = vec![open(bin)?, open(node)?];
    if !already_prepared {
        collect(code, &mut readonly)?;
    }
    mark("read-only paths checked", readonly.len());
    let mut writable = Vec::new();
    collect(state, &mut writable)?;
    mark("state paths checked", writable.len());
    // Every ACL update addresses one validated handle, never a recursive tree.
    let mut security_writes = 0;
    if !already_prepared {
        let read = FILE_GENERIC_READ | FILE_GENERIC_EXECUTE;
        for (index, entry) in readonly.iter().enumerate() {
            security_writes += grant(entry, sid, read, false)?;
            if index % 1024 == 0 {
                mark("permissions prepared", index + 1);
            }
        }
    }
    for entry in &writable {
        security_writes += grant(
            entry,
            sid,
            FILE_GENERIC_READ | FILE_GENERIC_WRITE | FILE_GENERIC_EXECUTE | DELETE,
            true,
        )?;
    }
    if tracing {
        eprintln!(
            "marea-agent · security updates ({security_writes} writes): {} ms",
            began.elapsed().as_millis()
        );
    }
    // This marker is in read-only bin, never in agent-controlled state. Package
    // replacement invalidates it; new code files inherit the package ACL.
    // Every writable state object is still validated on every launch.
    if !already_prepared {
        if cache.try_exists().map_err(|e| e.to_string())? {
            std::fs::remove_file(&cache).map_err(|e| e.to_string())?;
        }
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&cache)
            .map_err(|e| e.to_string())?;
        file.write_all(key.as_bytes()).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn retries_temporary_file_contention_without_relaxing_the_lock() {
        use std::{os::windows::fs::OpenOptionsExt, time::Duration};
        let path = std::env::temp_dir().join(format!(
            "marea-agent-contention-{}-ñ.txt",
            std::process::id()
        ));
        let file = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .share_mode(FILE_SHARE_READ)
            .open(&path)
            .unwrap();
        struct Cleanup(PathBuf);
        impl Drop for Cleanup {
            fn drop(&mut self) {
                let _ = std::fs::remove_file(&self.0);
            }
        }
        let _cleanup = Cleanup(path.clone());
        let release = std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(150));
            drop(file);
        });
        let result = open(&path);
        release.join().unwrap();
        let entry = result.unwrap();
        assert_eq!(
            std::fs::OpenOptions::new()
                .write(true)
                .open(&path)
                .unwrap_err()
                .raw_os_error(),
            Some(32)
        );
        drop(entry);
        std::fs::OpenOptions::new().write(true).open(&path).unwrap();
    }

    #[test]
    fn persistent_contention_reports_the_path_and_stops_startup() {
        use std::os::windows::fs::OpenOptionsExt;
        let path = std::env::temp_dir().join(format!(
            "marea-agent-persistent-lock-{}-ñ.txt",
            std::process::id()
        ));
        let file = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .share_mode(FILE_SHARE_READ)
            .open(&path)
            .unwrap();
        let began = Instant::now();
        let result = open(&path);
        let elapsed = began.elapsed();
        drop(file);
        std::fs::remove_file(&path).unwrap();
        let error = result.err().unwrap();
        assert!(error.contains(&path.display().to_string()), "{error}");
        assert!(error.contains("os error 32"), "{error}");
        assert!(elapsed >= Duration::from_secs(3), "{elapsed:?}");
        assert!(elapsed < Duration::from_secs(10), "{elapsed:?}");

        let began = Instant::now();
        let error = open(&path).err().unwrap();
        assert!(error.contains("os error 2"), "{error}");
        assert!(began.elapsed() < Duration::from_secs(1));
    }

    #[test]
    fn repeated_preparation_keeps_real_acl_and_label_without_rewriting() {
        use windows_sys::Win32::Security::Isolation::DeriveAppContainerSidFromAppContainerName;
        let root =
            std::env::temp_dir().join(format!("marea-agent-acl-test-{}", std::process::id()));
        std::fs::create_dir(&root).unwrap();
        let path = root.join("owned.txt");
        std::fs::write(&path, "fixture").unwrap();
        struct Cleanup(PathBuf);
        impl Drop for Cleanup {
            fn drop(&mut self) {
                let _ = std::fs::remove_file(self.0.join("owned.txt"));
                let _ = std::fs::remove_dir(&self.0);
            }
        }
        let _cleanup = Cleanup(root.clone());
        let mut sid = null_mut();
        assert_eq!(
            unsafe {
                DeriveAppContainerSidFromAppContainerName(
                    wide(format!("Pleamar.Marea.AclTest.{}", std::process::id())).as_ptr(),
                    &mut sid,
                )
            },
            0
        );
        struct Free(PSID);
        impl Drop for Free {
            fn drop(&mut self) {
                unsafe {
                    FreeSid(self.0);
                }
            }
        }
        let sid = Free(sid);
        let entry = open(&path).unwrap();
        let read = FILE_GENERIC_READ | FILE_GENERIC_EXECUTE;
        assert!(grant(&entry, sid.0, read, false).unwrap() > 0);
        assert_eq!(grant(&entry, sid.0, read, false).unwrap(), 0);
        let write = read | FILE_GENERIC_WRITE | DELETE;
        assert!(grant(&entry, sid.0, write, true).unwrap() > 0);
        assert_eq!(grant(&entry, sid.0, write, true).unwrap(), 0);
        let directory = open(&root).unwrap();
        assert!(grant(&directory, sid.0, write, true).unwrap() > 0);
        assert_eq!(grant(&directory, sid.0, write, true).unwrap(), 0);
        // Read Windows' resulting descriptor, not the requested access structure.
        let (mut acl, mut descriptor) = (null_mut(), null_mut());
        status(
            unsafe {
                GetSecurityInfo(
                    entry.handle.0,
                    SE_FILE_OBJECT,
                    DACL_SECURITY_INFORMATION,
                    null_mut(),
                    null_mut(),
                    &mut acl,
                    null_mut(),
                    &mut descriptor,
                )
            },
            "read test ACL",
        )
        .unwrap();
        let _descriptor = Local(descriptor);
        let trustee = TRUSTEE_W {
            pMultipleTrustee: null_mut(),
            MultipleTrusteeOperation: NO_MULTIPLE_TRUSTEE,
            TrusteeForm: TRUSTEE_IS_SID,
            TrusteeType: TRUSTEE_IS_UNKNOWN,
            ptstrName: sid.0.cast(),
        };
        let mut rights = 0;
        status(
            unsafe { GetEffectiveRightsFromAclW(acl, &trustee, &mut rights) },
            "read test rights",
        )
        .unwrap();
        assert_eq!(rights & write, write);
    }
    #[test]
    fn rejects_hard_links_before_touching_security() {
        let root =
            std::env::temp_dir().join(format!("marea-agent-link-test-{}", std::process::id()));
        std::fs::create_dir(&root).unwrap();
        let first = root.join("owned.txt");
        let second = root.join("alias.txt");
        std::fs::write(&first, "fixture").unwrap();
        std::fs::hard_link(&first, &second).unwrap();
        assert!(open(&second).err().unwrap().contains("hard link"));
        std::fs::remove_file(second).unwrap();
        std::fs::remove_file(first).unwrap();
        std::fs::remove_dir(root).unwrap();
    }
}
