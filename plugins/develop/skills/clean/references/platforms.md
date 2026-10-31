# Native cleanup operations

Check availability/permissions; no elevation or global configuration changes. These are inspection commands, not deletion scripts.

| Host | Memory | Disk | Processes/boundaries |
| --- | --- | --- | --- |
| Linux | `free -b` | `df -B1`; scoped `du -x` | `ps -eo pid,ppid,state,rss,comm --sort=-rss`; `findmnt`, `/proc/self/mountinfo` |
| macOS | `vm_stat`, `sysctl hw.memsize` | `df -k`, scoped `du -k`; convert units | `ps -axo pid,ppid,state,rss,command`; `mount`, links/handles |
| Windows PowerShell | `Get-CimInstance Win32_OperatingSystem` (physical memory KiB) | `Get-PSDrive -PSProvider FileSystem` / `Get-Volume`; `Get-Item -LiteralPath` | `Get-CimInstance Win32_Process`, `Get-Process`, `Get-Service`; Attributes/LinkType/Target/mountpoints |

- Use Finder/FileManager Trash, freedesktop Trash or Windows Recycle Bin; verify selected volume/path support and actual destination. Never substitute deletion without explicit authority.
- Discover scratch from actual environment/workspace metadata; no hardcoded temporary/workspace roots or default whole-profile scans. Missing optional paths are normal.
- Check reparse descendants on Windows, including logical-versus-allocated size; check same-device bind mounts on POSIX, not merely device boundaries. Unverifiable traversal/ownership/use means protected/blocked; continue other targets.
- Keep raw units consistent. Memory pressure/accounting differs by OS; unavailable comparisons stay unknown. Never use Linux `drop_caches`, macOS `purge` or forced working-set trimming to improve reported RAM.
