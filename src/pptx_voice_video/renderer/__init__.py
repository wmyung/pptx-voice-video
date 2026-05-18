from .libreoffice import LibreOfficeRenderer

def create_renderer(name: str, config):
    if name.lower() in {"libreoffice", "soffice"}: return LibreOfficeRenderer(config)
    raise ValueError(f"Unknown renderer: {name}")
