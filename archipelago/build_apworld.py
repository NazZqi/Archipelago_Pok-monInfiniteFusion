import os
import zipfile
import shutil

src_dir = os.path.join(os.path.dirname(__file__), "apworld_dev", "pokemon_infinite_fusion")
dest_zip = os.path.join(os.path.dirname(__file__), "..", "releases", "pokemon_infinite_fusion.apworld")

def build():
    # Asegurarnos de que el directorio destino existe
    os.makedirs(os.path.dirname(dest_zip), exist_ok=True)
    
    with zipfile.ZipFile(dest_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(src_dir):
            if "__pycache__" in root:
                continue
            for file in files:
                if file.endswith(".pyc"):
                    continue
                file_path = os.path.join(root, file)
                # El archivo debe estar dentro de la carpeta pokemon_infinite_fusion
                rel_path = os.path.relpath(file_path, src_dir)
                arcname = os.path.join("pokemon_infinite_fusion", rel_path)
                zipf.write(file_path, arcname)
    
    print(f"APWorld empaquetado exitosamente en: {dest_zip}")

if __name__ == "__main__":
    build()
