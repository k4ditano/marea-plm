use std::{
    collections::BTreeMap,
    ffi::{OsStr, OsString},
    io,
    mem::{size_of, zeroed},
    os::windows::ffi::OsStrExt,
    path::{Path, PathBuf},
    ptr::{null, null_mut},
};
use windows_sys::Win32::{
    Foundation::*,
    Security::{Authorization::*, Isolation::*, *},
    System::{
        Console::*, JobObjects::*, StationsAndDesktops::*, SystemInformation::GetWindowsDirectoryW,
        Threading::*,
    },
};

pub(super) type Result<T> = std::result::Result<T, String>;
pub(super) fn wide(value: impl AsRef<OsStr>) -> Vec<u16> {
    value.as_ref().encode_wide().chain(Some(0)).collect()
}
pub(super) fn ok(value: i32, operation: &str) -> Result<()> {
    if value != 0 {
        Ok(())
    } else {
        Err(format!("{operation}: {}", io::Error::last_os_error()))
    }
}
pub(super) fn status(value: u32, operation: &str) -> Result<()> {
    if value == 0 {
        Ok(())
    } else {
        Err(format!(
            "{operation}: {}",
            io::Error::from_raw_os_error(value as i32)
        ))
    }
}
pub(super) struct Handle(pub(super) HANDLE);
impl Handle {
    pub(super) fn new(value: HANDLE, operation: &str) -> Result<Self> {
        if value.is_null() || value == INVALID_HANDLE_VALUE {
            Err(format!("{operation}: {}", io::Error::last_os_error()))
        } else {
            Ok(Self(value))
        }
    }
}
impl Drop for Handle {
    fn drop(&mut self) {
        unsafe {
            CloseHandle(self.0);
        }
    }
}
struct Sid(PSID);
impl Drop for Sid {
    fn drop(&mut self) {
        unsafe {
            FreeSid(self.0);
        }
    }
}
pub(super) struct Local(pub(super) *mut std::ffi::c_void);
impl Drop for Local {
    fn drop(&mut self) {
        unsafe {
            LocalFree(self.0);
        }
    }
}

fn capability(name: &str) -> Result<Local> {
    let (mut groups, mut capabilities) = (null_mut(), null_mut());
    let (mut group_count, mut capability_count) = (0, 0);
    ok(
        unsafe {
            DeriveCapabilitySidsFromName(
                wide(name).as_ptr(),
                &mut groups,
                &mut group_count,
                &mut capabilities,
                &mut capability_count,
            )
        },
        "derive runtime capability",
    )?;
    let _groups = Local(groups.cast());
    let _capabilities = Local(capabilities.cast());
    for i in 0..group_count as usize {
        drop(Local(unsafe { *groups.add(i) }));
    }
    let mut result = None;
    for i in 0..capability_count as usize {
        let sid = Local(unsafe { *capabilities.add(i) });
        if i == 0 {
            result = Some(sid);
        }
    }
    result.ok_or_else(|| "Windows returned no runtime capability".into())
}

pub(super) fn sid_string(sid: PSID) -> Result<String> {
    let mut text = null_mut();
    ok(
        unsafe { ConvertSidToStringSidW(sid, &mut text) },
        "format security identity",
    )?;
    let _text = Local(text.cast());
    let mut length = 0;
    while unsafe { *text.add(length) } != 0 {
        length += 1;
    }
    String::from_utf16(unsafe { std::slice::from_raw_parts(text, length) })
        .map_err(|e| e.to_string())
}

struct Desktop {
    handle: HDESK,
    name: Vec<u16>,
}
impl Drop for Desktop {
    fn drop(&mut self) {
        unsafe {
            CloseDesktop(self.handle);
        }
    }
}
impl Desktop {
    fn new(package: PSID) -> Result<Self> {
        let mut token = null_mut();
        ok(
            unsafe { OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token) },
            "open host identity",
        )?;
        let token = Handle::new(token, "host identity")?;
        let mut data = [0usize; 32];
        let mut returned = 0;
        ok(
            unsafe {
                GetTokenInformation(
                    token.0,
                    TokenUser,
                    data.as_mut_ptr().cast(),
                    size_of_val(&data) as u32,
                    &mut returned,
                )
            },
            "read host identity",
        )?;
        let user = unsafe { &*data.as_ptr().cast::<TOKEN_USER>() };
        let sddl = wide(format!(
            "D:(A;;GA;;;SY)(A;;GA;;;{})(A;;0xC3;;;{})S:(ML;;NW;;;LW)",
            sid_string(user.User.Sid)?,
            sid_string(package)?
        ));
        let mut descriptor = null_mut();
        ok(
            unsafe {
                ConvertStringSecurityDescriptorToSecurityDescriptorW(
                    sddl.as_ptr(),
                    1,
                    &mut descriptor,
                    null_mut(),
                )
            },
            "create private desktop descriptor",
        )?;
        let _descriptor = Local(descriptor);
        let attributes = SECURITY_ATTRIBUTES {
            nLength: size_of::<SECURITY_ATTRIBUTES>() as u32,
            lpSecurityDescriptor: descriptor,
            bInheritHandle: 0,
        };
        let name = wide(format!("MareaAgent-{}", std::process::id()));
        // Never displayed or switched to; the worker has no access to the
        // user's interactive desktop. Existing desktop ACLs remain unchanged.
        let handle =
            unsafe { CreateDesktopW(name.as_ptr(), null(), null(), 0, GENERIC_ALL, &attributes) };
        if handle.is_null() {
            return Err(format!(
                "create private worker desktop: {}",
                io::Error::last_os_error()
            ));
        }
        Ok(Self { handle, name })
    }
}

fn profile_name(root: &Path) -> String {
    // A separate bundle has a separate identity, including isolated test bundles.
    let mut hash = 0xcbf29ce484222325u64;
    for word in root
        .as_os_str()
        .to_string_lossy()
        .to_lowercase()
        .encode_utf16()
    {
        for byte in word.to_le_bytes() {
            hash = (hash ^ byte as u64).wrapping_mul(0x100000001b3);
        }
    }
    format!("Pleamar.Marea.Agent.{hash:016x}")
}

fn profile(name: &[u16]) -> Result<Sid> {
    let mut sid = null_mut();
    let hr = unsafe {
        CreateAppContainerProfile(
            name.as_ptr(),
            wide("Marea AI").as_ptr(),
            wide("Marea isolated AI worker").as_ptr(),
            null(),
            0,
            &mut sid,
        )
    };
    if hr < 0 {
        if hr as u32 != 0x800700b7 {
            return Err(format!("CreateAppContainerProfile: HRESULT {hr:#x}"));
        }
        let hr = unsafe { DeriveAppContainerSidFromAppContainerName(name.as_ptr(), &mut sid) };
        if hr < 0 {
            return Err(format!("derive AppContainer identity: HRESULT {hr:#x}"));
        }
    }
    Ok(Sid(sid))
}

struct Attributes {
    _storage: Vec<u128>,
    list: LPPROC_THREAD_ATTRIBUTE_LIST,
}
impl Attributes {
    fn new(count: u32) -> Result<Self> {
        let mut bytes = 0;
        unsafe {
            InitializeProcThreadAttributeList(null_mut(), count, 0, &mut bytes);
        }
        let mut storage = vec![0u128; bytes.div_ceil(size_of::<u128>())];
        let list = storage.as_mut_ptr().cast();
        ok(
            unsafe { InitializeProcThreadAttributeList(list, count, 0, &mut bytes) },
            "initialize isolation attributes",
        )?;
        Ok(Self {
            _storage: storage,
            list,
        })
    }
    fn set<T>(&self, key: u32, value: &T) -> Result<()> {
        ok(
            unsafe {
                UpdateProcThreadAttribute(
                    self.list,
                    0,
                    key as usize,
                    (value as *const T).cast(),
                    size_of::<T>(),
                    null_mut(),
                    null(),
                )
            },
            "set isolation attribute",
        )
    }
}
impl Drop for Attributes {
    fn drop(&mut self) {
        unsafe {
            DeleteProcThreadAttributeList(self.list);
        }
    }
}

fn argument(value: &OsStr) -> Vec<u16> {
    let mut result = vec![b'"' as u16];
    let mut slashes = 0;
    for c in value.encode_wide() {
        if c == b'\\' as u16 {
            slashes += 1;
            continue;
        }
        result.extend(std::iter::repeat_n(
            b'\\' as u16,
            if c == b'"' as u16 {
                slashes * 2 + 1
            } else {
                slashes
            },
        ));
        slashes = 0;
        result.push(c);
    }
    result.extend(std::iter::repeat_n(b'\\' as u16, slashes * 2));
    result.push(b'"' as u16);
    result
}

fn inherited(which: u32) -> Result<Handle> {
    let original = unsafe { GetStdHandle(which) };
    if original.is_null() || original == INVALID_HANDLE_VALUE {
        return Err("the host needs piped stdin/stdout/stderr".into());
    }
    let mut copy = null_mut();
    ok(
        unsafe {
            DuplicateHandle(
                GetCurrentProcess(),
                original,
                GetCurrentProcess(),
                &mut copy,
                0,
                1,
                DUPLICATE_SAME_ACCESS,
            )
        },
        "duplicate protocol handle",
    )?;
    Handle::new(copy, "protocol handle")
}

fn verify_isolation(process: HANDLE, sid: PSID) -> Result<()> {
    let mut child_policy = 0u32;
    ok(
        unsafe {
            GetProcessMitigationPolicy(
                process,
                ProcessChildProcessPolicy,
                (&mut child_policy as *mut u32).cast(),
                4,
            )
        },
        "inspect child-process restriction",
    )?;
    if child_policy & 1 == 0 {
        return Err("worker can create child processes".into());
    }
    let mut token = null_mut();
    ok(
        unsafe { OpenProcessToken(process, TOKEN_QUERY | TOKEN_DUPLICATE, &mut token) },
        "open isolated token",
    )?;
    let token = Handle::new(token, "isolated token")?;
    let (mut value, mut returned) = (0u32, 0u32);
    ok(
        unsafe {
            GetTokenInformation(
                token.0,
                TokenIsAppContainer,
                (&mut value as *mut u32).cast(),
                4,
                &mut returned,
            )
        },
        "inspect isolated token",
    )?;
    if returned != 4 || value == 0 {
        return Err("worker is not an AppContainer".into());
    }
    let mut impersonation = null_mut();
    ok(
        unsafe { DuplicateToken(token.0, SecurityImpersonation, &mut impersonation) },
        "duplicate isolated token",
    )?;
    let impersonation = Handle::new(impersonation, "impersonation token")?;
    let sid_text = sid_string(sid)?;
    // Class 46 is rejected by GetTokenInformation on current Windows builds.
    // Check the required access semantics instead: our package grant works,
    // while an ALL APPLICATION PACKAGES grant alone must not grant access.
    for (package, expected) in [(sid_text.as_str(), true), ("AC", false)] {
        let sddl = wide(format!("O:SYG:SYD:(A;;0x1;;;WD)(A;;0x1;;;{package})"));
        let mut descriptor = null_mut();
        ok(
            unsafe {
                ConvertStringSecurityDescriptorToSecurityDescriptorW(
                    sddl.as_ptr(),
                    1,
                    &mut descriptor,
                    null_mut(),
                )
            },
            "build isolation check",
        )?;
        let _descriptor = Local(descriptor);
        let mapping = GENERIC_MAPPING {
            GenericRead: 1,
            GenericWrite: 1,
            GenericExecute: 1,
            GenericAll: 1,
        };
        let mut privileges = [0u64; 32];
        let mut length = size_of_val(&privileges) as u32;
        let (mut granted, mut allowed) = (0, 0);
        ok(
            unsafe {
                AccessCheck(
                    descriptor,
                    impersonation.0,
                    1,
                    &mapping,
                    privileges.as_mut_ptr().cast(),
                    &mut length,
                    &mut granted,
                    &mut allowed,
                )
            },
            "check isolated access",
        )?;
        if (allowed != 0 && granted & 1 != 0) != expected {
            return Err("worker does not enforce the required package access restrictions".into());
        }
    }
    Ok(())
}

fn environment(state: &Path, bin: &Path) -> Result<Vec<u16>> {
    let mut system = [0u16; 32768];
    let n = unsafe { GetWindowsDirectoryW(system.as_mut_ptr(), system.len() as u32) } as usize;
    if n == 0 || n >= system.len() {
        return Err("cannot find the Windows system directory".into());
    }
    use std::os::windows::ffi::OsStringExt;
    let mut env = BTreeMap::<OsString, OsString>::new();
    for key in ["HOME", "USERPROFILE", "MAREA_AGENT_DIR", "XDG_STATE_HOME"] {
        env.insert(key.into(), state.into());
    }
    for (key, folder) in [
        ("APPDATA", "config"),
        ("LOCALAPPDATA", "local"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_CACHE_HOME", "cache"),
        ("TEMP", "tmp"),
        ("TMP", "tmp"),
    ] {
        let path = state.join(folder);
        std::fs::create_dir_all(&path).map_err(|e| e.to_string())?;
        env.insert(key.into(), path.into());
    }
    env.insert("SystemRoot".into(), OsString::from_wide(&system[..n]));
    env.insert("PATH".into(), bin.into());
    for (key, value) in [
        ("MAREA_AGENT_PLATFORM", "windows-lpac"),
        ("PI_TELEMETRY", "0"),
        ("PI_OFFLINE", "1"),
        ("LANG", "C.UTF-8"),
    ] {
        env.insert(key.into(), value.into());
    }
    let mut entries: Vec<_> = env.into_iter().collect();
    entries.sort_by_key(|(key, _)| key.to_string_lossy().to_uppercase());
    let mut result = Vec::new();
    for (key, value) in entries {
        result.extend(key.encode_wide());
        result.push(b'=' as u16);
        result.extend(value.encode_wide());
        result.push(0);
    }
    result.push(0);
    Ok(result)
}

pub fn run() -> Result<u32> {
    let began = std::time::Instant::now();
    let tracing = std::env::var_os("MAREA_AGENT_TRACE").is_some_and(|value| value == "1");
    let mark = |stage: &str| {
        if tracing {
            eprintln!("marea-agent · {stage}: {} ms", began.elapsed().as_millis());
        }
    };
    let exe = std::env::current_exe()
        .map_err(|e| e.to_string())?
        .canonicalize()
        .map_err(|e| e.to_string())?;
    let bin = exe.parent().ok_or("missing executable directory")?;
    let root = bin.parent().ok_or("missing package directory")?;
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let validating = args
        .first()
        .is_some_and(|a| a == "--validate-worker" || a == "--remove-validation-profile");
    let name = wide(format!(
        "{}{}",
        profile_name(root),
        if validating { ".Validation" } else { "" }
    ));
    if args.as_slice() == [OsString::from("--remove-profile")]
        || args.as_slice() == [OsString::from("--remove-validation-profile")]
    {
        // Windows also returns success for an already absent profile.
        let hr = unsafe { DeleteAppContainerProfile(name.as_ptr()) };
        return if hr >= 0 {
            let cache = crate::path_access::cache_path(bin, validating);
            match std::fs::remove_file(cache) {
                Ok(()) => (),
                Err(e) if e.kind() == io::ErrorKind::NotFound => (),
                Err(e) => return Err(format!("remove package permission cache: {e}")),
            }
            Ok(0)
        } else {
            Err(format!("remove AppContainer profile: HRESULT {hr:#x}"))
        };
    }
    let probe = args.first().is_some_and(|a| a == "--probe");
    let prepare = args.first().is_some_and(|a| a == "--prepare");
    let args = if probe || prepare || validating {
        &args[1..]
    } else {
        &args[..]
    };
    let default_state = PathBuf::from(
        std::env::var_os("LOCALAPPDATA").ok_or("LOCALAPPDATA is missing")?,
    )
    .join(if validating {
        "Marea/AgentValidation"
    } else {
        "Marea/Agent"
    });
    let state = match args {
        [] => default_state.clone(),
        [flag, path] if flag == "--state" => PathBuf::from(path),
        _ => {
            return Err(
                "usage: marea-agent [--prepare|--probe|--validate-worker] [--state PATH]".into(),
            );
        }
    };
    // Test bundles may use their own state directory, never an arbitrary user folder.
    let expected = if probe {
        root.join("state")
    } else {
        default_state
    };
    let expected_parent = expected.parent().ok_or("state has no parent")?;
    std::fs::create_dir_all(expected_parent).map_err(|e| e.to_string())?;
    let expected_parent = expected_parent.canonicalize().map_err(|e| e.to_string())?;
    let chosen_parent = state
        .parent()
        .ok_or("state has no parent")?
        .canonicalize()
        .map_err(|e| e.to_string())?;
    if chosen_parent != expected_parent || state.file_name() != expected.file_name() {
        return Err("state must be the dedicated Marea agent directory".into());
    }
    std::fs::create_dir_all(&state).map_err(|e| e.to_string())?;
    let state = state.canonicalize().map_err(|e| e.to_string())?;
    if state.parent() != Some(expected_parent.as_path()) {
        return Err("state cannot be a directory link outside its parent".into());
    }
    let code = root
        .join("app/agent")
        .canonicalize()
        .map_err(|e| format!("missing packaged AI worker: {e}"))?;
    if code != root.join("app/agent") {
        return Err("worker directory must not redirect outside its package".into());
    }
    let node = bin.join("node.exe");
    if !node.is_file() {
        return Err("bundled node.exe is missing".into());
    }
    let entry = code.join(if probe {
        "sandbox-probe.mjs"
    } else {
        "worker.mjs"
    });
    if !entry.is_file() {
        return Err("packaged worker entry point is missing".into());
    }
    mark("paths validated");
    let sid = profile(&name)?;
    mark("profile ready");
    crate::path_access::prepare(bin, &node, &code, &state, sid.0, validating)?;
    mark("permissions ready");
    let env = environment(&state, bin)?;
    if prepare {
        return Ok(0);
    }

    let mut internet = [0u32; 17];
    let mut size = size_of_val(&internet) as u32;
    ok(
        unsafe {
            CreateWellKnownSid(
                WinCapabilityInternetClientSid,
                null_mut(),
                internet.as_mut_ptr().cast(),
                &mut size,
            )
        },
        "create internet capability",
    )?;
    // Winsock reads its Windows provider catalogue during WSAStartup.
    let registry = capability("registryRead")?;
    let mut allowed = [
        SID_AND_ATTRIBUTES {
            Sid: internet.as_mut_ptr().cast(),
            Attributes: 4,
        },
        SID_AND_ATTRIBUTES {
            Sid: registry.0,
            Attributes: 4,
        },
    ];
    let capabilities = SECURITY_CAPABILITIES {
        AppContainerSid: sid.0,
        Capabilities: allowed.as_mut_ptr(),
        CapabilityCount: allowed.len() as u32,
        Reserved: 0,
    };
    let lpac = 1u32; // PROCESS_CREATION_ALL_APPLICATION_PACKAGES_OPT_OUT
    let no_children = 1u32; // PROCESS_CREATION_CHILD_PROCESS_RESTRICTED
    let handles = [
        inherited(STD_INPUT_HANDLE)?,
        inherited(STD_OUTPUT_HANDLE)?,
        inherited(STD_ERROR_HANDLE)?,
    ];
    let inherited_handles = handles.each_ref().map(|h| h.0);
    let attributes = Attributes::new(4)?;
    attributes.set(PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES, &capabilities)?;
    attributes.set(PROC_THREAD_ATTRIBUTE_ALL_APPLICATION_PACKAGES_POLICY, &lpac)?;
    attributes.set(PROC_THREAD_ATTRIBUTE_CHILD_PROCESS_POLICY, &no_children)?;
    attributes.set(PROC_THREAD_ATTRIBUTE_HANDLE_LIST, &inherited_handles)?;
    let job = Handle::new(
        unsafe { CreateJobObjectW(null(), null()) },
        "create worker job",
    )?;
    let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = unsafe { zeroed() };
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        | JOB_OBJECT_LIMIT_PROCESS_MEMORY;
    limits.BasicLimitInformation.ActiveProcessLimit = 1;
    limits.ProcessMemoryLimit = 512 * 1024 * 1024;
    ok(
        unsafe {
            SetInformationJobObject(
                job.0,
                JobObjectExtendedLimitInformation,
                (&limits as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
                size_of_val(&limits) as u32,
            )
        },
        "limit worker resources",
    )?;

    let mut command = Vec::new();
    for arg in [
        node.as_os_str(),
        OsStr::new("--preserve-symlinks"),
        OsStr::new("--preserve-symlinks-main"),
        OsStr::new("--max-old-space-size=128"),
        OsStr::new("--max-semi-space-size=4"),
        entry.as_os_str(),
    ] {
        if !command.is_empty() {
            command.push(b' ' as u16);
        }
        command.extend(argument(arg));
    }
    command.push(0);
    let mut desktop = Desktop::new(sid.0)?;
    mark("private desktop ready");
    let mut startup: STARTUPINFOEXW = unsafe { zeroed() };
    startup.StartupInfo.cb = size_of_val(&startup) as u32;
    startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
    startup.StartupInfo.hStdInput = inherited_handles[0];
    startup.StartupInfo.hStdOutput = inherited_handles[1];
    startup.StartupInfo.hStdError = inherited_handles[2];
    startup.StartupInfo.lpDesktop = desktop.name.as_mut_ptr();
    startup.lpAttributeList = attributes.list;
    let mut process: PROCESS_INFORMATION = unsafe { zeroed() };
    // CREATE_NO_WINDOW still initializes a console, which conflicts with the
    // child-process restriction. Detached Node uses only our explicit pipes.
    ok(
        unsafe {
            CreateProcessW(
                wide(&node).as_ptr(),
                command.as_mut_ptr(),
                null(),
                null(),
                1,
                DETACHED_PROCESS
                    | CREATE_SUSPENDED
                    | CREATE_UNICODE_ENVIRONMENT
                    | EXTENDED_STARTUPINFO_PRESENT,
                env.as_ptr().cast(),
                wide(&state).as_ptr(),
                &startup.StartupInfo,
                &mut process,
            )
        },
        "create isolated worker",
    )?;
    let thread = Handle::new(process.hThread, "worker thread")?;
    mark("worker created suspended");
    let child = Handle::new(process.hProcess, "worker process")?;
    let configured = (|| {
        ok(
            unsafe { AssignProcessToJobObject(job.0, child.0) },
            "contain worker lifetime",
        )?;
        verify_isolation(child.0, sid.0)?;
        if unsafe { ResumeThread(thread.0) } == u32::MAX {
            return Err(format!("resume worker: {}", io::Error::last_os_error()));
        }
        Ok(())
    })();
    if let Err(error) = configured {
        unsafe {
            TerminateProcess(child.0, 3);
        }
        return Err(error);
    }
    mark("worker resumed");
    if unsafe { WaitForSingleObject(child.0, INFINITE) } != WAIT_OBJECT_0 {
        return Err("waiting for isolated worker failed".into());
    }
    let mut code = 0;
    ok(
        unsafe { GetExitCodeProcess(child.0, &mut code) },
        "worker exit code",
    )?;
    Ok(code)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn quotes_preserve_spaces_unicode_backslashes_and_quotes() {
        let quote = |s: &str| String::from_utf16(&argument(OsStr::new(s))).unwrap();
        assert_eq!(quote("C:\\Marea ñ\\"), "\"C:\\Marea ñ\\\\\"");
        assert_eq!(quote("a\"b"), "\"a\\\"b\"");
        assert_eq!(quote(""), "\"\"");
    }
}
