import io, zipfile
from typing import Tuple

def get_txx_from_txxx(txxx_file:bytes, txxx_file_name:str) -> Tuple[str, bytes]:
    """
    Extract the .twb file from a .twbx file. Or the .tds file from a .tdsx file.
    """
    file_type = txxx_file_name.split(".")[-1]
    file_type_desired = file_type[:-1]
    
    with zipfile.ZipFile(io.BytesIO(txxx_file), "r") as zip_ref:
        # Find the file_type_desired file in the archive
        txx_files = [f for f in zip_ref.namelist() if f.endswith(file_type_desired) and "/" not in f]
        if not txx_files:
            raise FileNotFoundError(f"No top-level { file_type_desired } file found in the TXXX archive.")
        if len(txx_files) > 1:
            raise ValueError(f"Multiple top-level { file_type_desired } files found in the TXXX archive. Wait, what?")
        
        txx_file_name = txx_files[0]
        txx_content = zip_ref.read(txx_file_name).decode("utf-8")
        
        return txx_file_name, txx_content
