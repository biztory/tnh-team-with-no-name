import io, zipfile, re
from typing import Tuple

from tableau_next_question.functions import log_and_display_message

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


def tableau_core_field_ref_to_components(field_ref:str) -> dict:
    """
    Takes a field reference from a Tableau workbook (e.g.: `[sqlproxy.05q18151cyifxn14m2uyh05aqp5y].[sum:distance_km:qk]`) and returns a dictionary with its components (agg, name, role_category).
    """

    try:
        field_ref_matches = re.match(r".+\[(\w+):([\w\_\d]+):(\w+)\]", field_ref)
        if field_ref_matches is not None:
            field_ref_agg = field_ref_matches.groups()[0]
            field_ref_name = field_ref_matches.groups()[1]
            field_ref_role_category = field_ref_matches.groups()[2]

        return {
            "agg": field_ref_agg,
            "name": field_ref_name,
            "role_category": field_ref_role_category
        }
    except Exception as e:
        log_and_display_message(f"Error parsing field reference '{ field_ref }': { e }", level="error")
        return {
            "agg": None,
            "name": None,
            "role_category": None
        }