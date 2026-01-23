Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -like "*main.py*" } | Select-Object ProcessId, CommandLine

Stop-Process -Id 46956 -Force