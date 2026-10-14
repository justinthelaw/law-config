# Platform inspection

These are read-only starting points, not a deletion script. Check command availability and permissions. Do not elevate or change global host configuration for cleanup.

| Host | Memory | Disk | Processes and boundaries |
| --- | --- | --- | --- |
| Linux | `free -b` (available memory) | `df -B1` for affected mounts; `du -x` on scoped candidates | `ps -eo pid,ppid,state,rss,comm --sort=-rss`; `findmnt` and `/proc/self/mountinfo` |
| macOS | `vm_stat` and `sysctl hw.memsize`; pressure interpretation differs from Linux | `df -k` and `du -k` with explicit unit conversion | `ps -axo pid,ppid,state,rss,command`; `mount`; inspect symlinks and active handles |
| Windows PowerShell | `Get-CimInstance Win32_OperatingSystem` (FreePhysicalMemory/TotalVisibleMemorySize are KiB) | `Get-PSDrive -PSProvider FileSystem` or `Get-Volume`; `Get-Item -LiteralPath` for candidates | `Get-CimInstance Win32_Process`, `Get-Process`, `Get-Service`; inspect Attributes/LinkType/Target and volume mountpoints |

Discover actual scratch roots from the host's environment and workspace metadata; never hard-code `/tmp`, `/workspace` or `C:\workspace` as authorized removal scope. Optional paths may not exist. Do not scan entire user profiles by default.

On Windows, directory logical `Length` sums do not prove allocated bytes. Reparse-point descendants require explicit inspection before recursive traversal. On POSIX, check same-device bind mounts in addition to device boundaries. If safe descendant traversal, ownership or active-use checks are unavailable, mark the candidate protected/blocked and proceed with other targets.

Keep raw readings and units consistent. Do not write Linux `drop_caches`, run macOS `purge`, or force process working-set trimming just to improve a displayed RAM number. If comparable memory accounting is unavailable, report it as unavailable rather than inventing a reclaimed value.
