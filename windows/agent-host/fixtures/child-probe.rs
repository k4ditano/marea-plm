#[cfg(windows)]
fn main() {
    use std::{
        mem::{size_of_val, zeroed},
        os::windows::ffi::OsStrExt,
        ptr::null,
    };
    use windows_sys::Win32::{Foundation::*, System::Threading::*};
    if std::env::args().any(|arg| arg == "--child") {
        return;
    }
    let path = std::env::current_exe().unwrap();
    let application: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
    let mut command: Vec<u16> = format!("\"{}\" --child", path.display())
        .encode_utf16()
        .chain(Some(0))
        .collect();
    let mut startup: STARTUPINFOW = unsafe { zeroed() };
    startup.cb = size_of_val(&startup) as u32;
    let mut process: PROCESS_INFORMATION = unsafe { zeroed() };
    let mut policy = 0u32;
    let inspected = unsafe {
        GetProcessMitigationPolicy(
            GetCurrentProcess(),
            ProcessChildProcessPolicy,
            (&mut policy as *mut u32).cast(),
            4,
        )
    } != 0;
    let created = unsafe {
        CreateProcessW(
            application.as_ptr(),
            command.as_mut_ptr(),
            null(),
            null(),
            0,
            DETACHED_PROCESS,
            null(),
            null(),
            &startup,
            &mut process,
        )
    } != 0;
    let error = unsafe { GetLastError() };
    if created {
        unsafe {
            TerminateProcess(process.hProcess, 0);
            CloseHandle(process.hThread);
            CloseHandle(process.hProcess);
        }
    }
    let denied = !created && error == ERROR_CHILD_PROCESS_BLOCKED && inspected && policy & 1 != 0;
    println!(
        "{{\"childDenied\":{denied},\"created\":{created},\"win32Error\":{error},\"policy\":{policy}}}"
    );
    std::process::exit(if denied { 0 } else { 1 });
}

#[cfg(not(windows))]
fn main() {
    panic!("This fixture requires Windows");
}
