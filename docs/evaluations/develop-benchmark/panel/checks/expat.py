import os, pathlib, subprocess, tempfile
xmlwf = next(p for p in pathlib.Path("build-panel").rglob("xmlwf") if p.is_file() and os.access(p,os.X_OK))
def inspect(data):
    with tempfile.TemporaryDirectory() as folder:
        doc=pathlib.Path(folder)/"document.xml"; doc.write_text(data)
        p=subprocess.run([str(xmlwf.resolve()),str(doc)],capture_output=True)
        return p.returncode, (p.stdout+p.stderr).decode(errors="replace")
if os.environ["PANEL_STAGE"] == "preserve":
    ok = inspect('<!DOCTYPE r [<!ENTITY ok "text">]><r>&ok;</r>')[0] == 0 and inspect("<a></b>")[0] != 0
    code,output=inspect('<!DOCTYPE r [<!ENTITY loop "&loop;">]><r>&loop;</r>')
    print("recursive entity",code,output[:180])
    ok = ok and code!=0 and "recursive" in output.lower()
else:
    table=[]
    for opening,closing in [("<![CDATA[","]]>"),("<!--","-->"),("<?note ","?>")]:
        literal=opening+("&payload;"*650)+closing
        data='<!DOCTYPE r [<!ENTITY payload "'+("q"*18000)+'"><!ENTITY literal "'+literal+'">]><r>&literal;</r>'
        code,output=inspect(data);table.append(code==0);print(opening,code,output[:180])
    data='<!DOCTYPE r [<!ENTITY payload "'+("q"*18000)+'"><!ENTITY real "'+("&payload;"*650)+'">]><r>&real;</r>'
    code,output=inspect(data);print("real expansion",code,output[:180]);table.append(code!=0 and "amplification" in output.lower())
    ok=all(table)
raise SystemExit(0 if ok else 42)
