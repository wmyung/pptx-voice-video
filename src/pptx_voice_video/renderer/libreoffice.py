from __future__ import annotations
import shutil, subprocess, tempfile
from pathlib import Path

class LibreOfficeRenderer:
    name="libreoffice"
    def __init__(self, config): self.config=config
    def health_check(self)->dict:
        exe=shutil.which('soffice') or shutil.which('libreoffice')
        return {"renderer": self.name, "available": bool(exe), "path": exe}
    def render(self, pptx: Path, output_dir: Path) -> list[Path]:
        exe=shutil.which('soffice') or shutil.which('libreoffice')
        output_dir.mkdir(parents=True, exist_ok=True)
        tmp=Path(tempfile.mkdtemp(prefix='pptx_render_'))
        if pptx.suffix.lower() == '.pdf':
            pdf=pptx
        else:
            if not exe: raise RuntimeError("LibreOffice/soffice not found. Install libreoffice for slide rendering.")
            subprocess.run([exe,'--headless','--convert-to','pdf','--outdir',str(tmp),str(pptx)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            pdf=tmp/(pptx.stem+'.pdf')
            if not pdf.exists():
                found=list(tmp.glob('*.pdf'))
                if not found: raise RuntimeError("LibreOffice did not produce a PDF")
                pdf=found[0]
        prefix=output_dir/'slide'
        subprocess.run(['pdftoppm','-png','-r','150',str(pdf),str(prefix)], check=True)
        imgs=sorted(output_dir.glob('slide-*.png'))
        final=[]
        for i,p in enumerate(imgs,1):
            dst=output_dir/f"slide_{i:03}.png"
            if p != dst: p.replace(dst)
            final.append(dst)
        return final
