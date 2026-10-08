# WScript.Shell's Arguments property uses the ANSI shell-link interface and
# loses characters outside the current code page. Keep all link fields UTF-16.
if (-not ('Marea.Windows.Shortcuts' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

namespace Marea.Windows {
    [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IShellLinkW {
        void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path, int capacity, IntPtr findData, uint flags);
        void GetIDList(out IntPtr list);
        void SetIDList(IntPtr list);
        void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder value, int capacity);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string value);
        void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder value, int capacity);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string value);
        void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder value, int capacity);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string value);
        void GetHotkey(out short value);
        void SetHotkey(short value);
        void GetShowCmd(out int value);
        void SetShowCmd(int value);
        void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path, int capacity, out int index);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string path, int index);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string path, uint reserved);
        void Resolve(IntPtr window, uint flags);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string path);
    }

    public sealed class ShortcutInfo {
        public string Target;
        public string Arguments;
        public string WorkingDirectory;
        public string Description;
        public string Icon;
        public int IconIndex;
    }

    public static class Shortcuts {
        private static object NewLink() {
            return Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("00021401-0000-0000-C000-000000000046"), true));
        }
        private static string Text(string value) {
            if (value == null || value.IndexOf('\0') >= 0 || value.Length >= 32768)
                throw new ArgumentException("Invalid shortcut field.");
            return value;
        }
        public static void Create(string path, string target, string arguments, string directory, string description) {
            Create(path, target, arguments, directory, description, "");
        }
        public static void Create(string path, string target, string arguments, string directory, string description, string icon) {
            path = Path.GetFullPath(Text(path));
            if (!String.Equals(Path.GetExtension(path), ".lnk", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("A shortcut path must end in .lnk.");
            if (File.Exists(path) || Directory.Exists(path))
                throw new IOException("Shortcut already exists: " + path);
            string temporary = Path.Combine(Path.GetDirectoryName(path), ".marea-" + Guid.NewGuid().ToString("N") + ".lnk");
            object instance = NewLink();
            try {
                IShellLinkW link = (IShellLinkW)instance;
                link.SetPath(Text(target));
                link.SetArguments(Text(arguments));
                link.SetWorkingDirectory(Text(directory));
                link.SetDescription(Text(description));
                if (icon.Length != 0) link.SetIconLocation(Path.GetFullPath(Text(icon)), 0);
                ((IPersistFile)instance).Save(temporary, true);
                // File.Move on the supported .NET runtimes refuses to replace
                // a destination created by another installer in the meantime.
                File.Move(temporary, path);
            } finally {
                Marshal.FinalReleaseComObject(instance);
                if (File.Exists(temporary)) File.Delete(temporary);
            }
        }
        public static void SetIcon(string path, string icon) {
            path = Path.GetFullPath(Text(path));
            icon = Path.GetFullPath(Text(icon));
            if (!File.Exists(icon)) throw new FileNotFoundException("Missing shortcut icon.", icon);
            object instance = NewLink();
            try {
                ((IPersistFile)instance).Load(path, 2);
                ((IShellLinkW)instance).SetIconLocation(icon, 0);
                ((IPersistFile)instance).Save(path, true);
            } finally { Marshal.FinalReleaseComObject(instance); }
        }
        public static ShortcutInfo Read(string path) {
            object instance = NewLink();
            try {
                ((IPersistFile)instance).Load(Path.GetFullPath(Text(path)), 0);
                IShellLinkW link = (IShellLinkW)instance;
                StringBuilder target = new StringBuilder(32768), arguments = new StringBuilder(32768);
                StringBuilder directory = new StringBuilder(32768), description = new StringBuilder(32768);
                StringBuilder icon = new StringBuilder(32768);
                int iconIndex;
                link.GetPath(target, target.Capacity, IntPtr.Zero, 4); // SLGP_RAWPATH; never resolve/launch a target.
                link.GetArguments(arguments, arguments.Capacity);
                link.GetWorkingDirectory(directory, directory.Capacity);
                link.GetDescription(description, description.Capacity);
                link.GetIconLocation(icon, icon.Capacity, out iconIndex);
                return new ShortcutInfo { Target=target.ToString(), Arguments=arguments.ToString(),
                    WorkingDirectory=directory.ToString(), Description=description.ToString(),
                    Icon=icon.ToString(), IconIndex=iconIndex };
            } finally { Marshal.FinalReleaseComObject(instance); }
        }
    }
}
'@
}
