' DevOps Manager — Silent Windows launcher
' Double-click this file to start the app with NO terminal window.
Option Explicit

Dim oShell, oFSO, strRoot, strPython, strMain

Set oShell = CreateObject("WScript.Shell")
Set oFSO   = CreateObject("Scripting.FileSystemObject")

' Script lives in <root>\scripts\win\, so three levels up to reach project root
strRoot   = oFSO.GetParentFolderName(oFSO.GetParentFolderName(oFSO.GetParentFolderName(WScript.ScriptFullName)))
strPython = strRoot & "\.venv\Scripts\pythonw.exe"
strMain   = strRoot & "\main.py"

If Not oFSO.FileExists(strPython) Then
    MsgBox "Virtual environment not found." & vbCrLf & vbCrLf & _
           "Expected path:" & vbCrLf & strPython & vbCrLf & vbCrLf & _
           "Run 'scripts\win\install.bat' from the project root first.", _
           vbCritical, "DevOps Manager"
    WScript.Quit 1
End If

' windowStyle 0 = completely hidden — no CMD, no flash
oShell.Run Chr(34) & strPython & Chr(34) & " " & Chr(34) & strMain & Chr(34), 0, False
