import copy

import core.functions.helpers_other as helpers_other

def copy_viz_with_changes(source_viz:dict, new_name:str="Viz_Copy", new_label:str="Copied Viz") -> dict:
    """
    Create a copy of a Visualization dictionary, with some changes (e.g. rows pill substituted).

    """
    
    target_viz = copy.deepcopy(source_viz)
    target_viz["name"] = new_name
    target_viz["label"] = new_label
    # Change "Sub-Category" on rows to "Category"
    # 1. Identify the field "id"
    sub_category_field_id = next((field_id for field_id in target_viz["fields"] if target_viz["fields"][field_id]["fieldName"] == "Sub_Category1"), None)
    category_field_id = next((field_id for field_id in target_viz["fields"] if target_viz["fields"][field_id]["fieldName"] == "Category1"), None)
    # 2. Substitute that "id" reference on rows
    target_viz["visualSpecification"]["rows"] = [category_field_id]
    # 3. Copy the headers specs for that field as it is used on rows/headers
    target_viz["visualSpecification"]["style"]["headers"][category_field_id] = target_viz["visualSpecification"]["style"]["headers"][sub_category_field_id]
    target_viz["visualSpecification"]["style"]["headers"].pop(sub_category_field_id, None) # Remove the old field from headers

    # Drop viz definition fields that we're not supposed to provide
    # General field names to drop (we don't want those anywhere in the dictionary)
    undesirable_general_fields_list = ["id", "url"]
    # Traverse the whole dictionary to remove these
    helpers_other.remove_fields_from_dictionary(target_viz, undesirable_general_fields_list)

    # Specific fields to drop
    undesirable_top_level_fields_list = ["id", "createdBy", "createdDate", "lastModifiedBy", "lastModifiedDate", "url", "permissions"]
    for undesirable_field in undesirable_top_level_fields_list:
        target_viz.pop(undesirable_field, None)
    undesirable_view_fields_list = ["isOriginal"]
    for undesirable_field in undesirable_view_fields_list:
        target_viz["view"].pop(undesirable_field, None)

    return target_viz