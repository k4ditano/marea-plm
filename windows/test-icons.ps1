param(
    [string]$Icon = (Join-Path $PSScriptRoot '../assets/marea.ico'),
    [string]$Setup,
    [string]$Uninstaller,
    [string]$Shortcut
)
$ErrorActionPreference = 'Stop'
$Icon = (Resolve-Path -LiteralPath $Icon).Path
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Runtime.InteropServices;
namespace Marea.Windows {
    public static class IconChecks {
        [DllImport("user32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        static extern IntPtr LoadImage(IntPtr instance, string path, uint type, int x, int y, uint flags);
        [DllImport("user32.dll")] static extern bool DestroyIcon(IntPtr icon);
        [DllImport("shell32.dll", CharSet=CharSet.Unicode)]
        static extern uint ExtractIconEx(string path, int index, IntPtr[] large, IntPtr[] small, uint count);
        public static void CheckSizes(string path) {
            foreach (int size in new int[] {16,20,24,32,40,48,64,96,128,256}) {
                IntPtr handle = LoadImage(IntPtr.Zero, path, 1, size, size, 0x10);
                if (handle == IntPtr.Zero) throw new Exception("Windows could not load icon size " + size);
                try {
                    using (Bitmap bitmap = Icon.FromHandle(handle).ToBitmap()) {
                        if (bitmap.Width != size || bitmap.Height != size || bitmap.GetPixel(0,0).A != 0)
                            throw new Exception("Icon size or transparent background was lost.");
                    }
                } finally { DestroyIcon(handle); }
            }
        }
        public static void CheckExecutable(string executable, string source) {
            IntPtr[] large = new IntPtr[1], small = new IntPtr[1];
            try {
                uint count = ExtractIconEx(executable, 0, large, small, 1);
                if (count == 0 || count == UInt32.MaxValue)
                    throw new Exception("No application icon in " + executable);
                foreach (IntPtr handle in new IntPtr[] {large[0], small[0]}) {
                    if (handle == IntPtr.Zero) throw new Exception("Missing executable icon size.");
                    using (Bitmap actual = Icon.FromHandle(handle).ToBitmap()) {
                        IntPtr expected = LoadImage(IntPtr.Zero, source, 1, actual.Width, actual.Height, 0x10);
                        if (expected == IntPtr.Zero) throw new Exception("Cannot load reference icon.");
                        try {
                            using (Bitmap reference = Icon.FromHandle(expected).ToBitmap()) {
                                for (int y=0; y<actual.Height; y++) for (int x=0; x<actual.Width; x++) {
                                    if (actual.GetPixel(x,y) != reference.GetPixel(x,y))
                                        throw new Exception("Executable does not contain the Marea icon: " + executable);
                                }
                            }
                        } finally { DestroyIcon(expected); }
                    }
                }
            } finally {
                if (large[0] != IntPtr.Zero) DestroyIcon(large[0]);
                if (small[0] != IntPtr.Zero) DestroyIcon(small[0]);
            }
        }
    }
}
'@
[Marea.Windows.IconChecks]::CheckSizes($Icon)
foreach ($binary in @($Setup, $Uninstaller)) {
    if ($binary) { [Marea.Windows.IconChecks]::CheckExecutable((Resolve-Path -LiteralPath $binary).Path, $Icon) }
}
if ($Shortcut) {
    . (Join-Path $PSScriptRoot 'shortcuts.ps1')
    $link = [Marea.Windows.Shortcuts]::Read($Shortcut)
    if ($link.Icon -ne $Icon -or $link.IconIndex -ne 0) { throw 'Installed shortcut does not use the packaged Marea icon.' }
}
Write-Host 'PASS: Windows loads all ten transparent icon sizes; supplied executable and shortcut icons match Marea'
