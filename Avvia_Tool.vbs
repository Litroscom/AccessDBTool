Set oShell = CreateObject("WScript.Shell")
strDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
oShell.CurrentDirectory = strDir
oShell.Run "pythonw.exe """ & strDir & "\access_db_tool.pyw""", 0, False
