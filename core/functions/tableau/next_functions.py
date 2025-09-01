from typing import Tuple
import copy, re
import traceback
import xml.etree.ElementTree as ET

import core.functions.helpers_other as helpers_other
import core.functions.templates.tableau_next as tableau_next_templates
import core.functions.tableau.documents as tableau_documents
from tableau_next_question.functions import log_and_display_message

aggregation_mapping_core_to_next = {
    "sum": "Sum",
    "avg": "Average",
    "min": "Minimum",
    "max": "Maximum",
    "count": "Count"
}

viewpoint_zoom_core_to_next = {
    "entire-view": "Entire",
    "fit-width": "Width",
    "fit-height": "Height",
    "normal": "Normal"
}

def find_matching_field_in_semantic_model(field_name:str, semantic_model_data_object:dict) -> dict:
    """
    Find a matching field in the semantic model data object by its API name. Accounts for the fact that sometimes, Tableau Next likes to add random numeric suffixes to field API names (e.g. "last_name" could just as well be "last_name5"). In that case, it might be best to use dataObjectFieldName (without the __c suffic)
    """
    matching_field = next((f for f in semantic_model_data_object.get("semanticDimensions", []) + semantic_model_data_object.get("semanticMeasurements", []) if f.get("apiName", "!").lower() == field_name.lower()), None)
    if matching_field is None:
        # Try to find a field with the same name, but with a numeric suffix
        matching_field = next((f for f in semantic_model_data_object.get("semanticDimensions", []) + semantic_model_data_object.get("semanticMeasurements", []) if f.get("dataObjectFieldName", "!").lower().startswith(field_name.lower())), None)
    return matching_field

def field_definition_from_semantic_model_field(semantic_model_field:dict, semantic_model_data_object:dict, aggregation:str="none") -> dict:
    """
    Creates a field definition that can be injected in a Visualization JSON definition, from a semantic model field. Can then be used with its "field reference" ("F1", ...) in different places in the visualization.

    Arguments:
    - semantic_model_field: A dictionary representing a semantic model field, coming from the API (semanticModel -> semanticDataObjects -> 0 -> semanticDimensions+semanticMeasurements -> <field>).
    - semantic_model_data_object: the combination of dimensions and measures in the semantic model data object, used to identify whether the field is a dimension or a measure.
    - aggregation: The aggregation type to apply to the field, probably only if it's a measure. Defaults to "none" because that is also the value we could have read from the XML.
    """

    field_definition = copy.deepcopy(tableau_next_templates.visualization_field_template)
    # Update all relevant properties
    field_definition["fieldName"] = semantic_model_field.get("apiName")
    field_definition["displayCategory"] = semantic_model_field.get("displayCategory")
    # field_definition["id"] = semantic_model_field.get("id")
    field_definition["role"] = "Dimension" if semantic_model_field.get("id") in [d.get("id") for d in semantic_model_data_object.get("semanticDimensions", [])] else "Measure"
    # If a measure, see if we have an aggregation
    if aggregation != "none":
        field_definition["function"] = aggregation_mapping_core_to_next.get(aggregation, "Sum")
    field_definition["objectName"] = semantic_model_data_object.get("apiName")

    return field_definition

def get_computed_sort_from_xml(selected_worksheet_elem: ET.Element, field: str) -> dict:
    """
    Take a worksheet element, and determine which computed sort might apply to a specific field.
    """

    applicable_computed_sorts = selected_worksheet_elem.find(f".//computed-sort[@column='{ field }']")
    if applicable_computed_sorts is not None:
        applicable_computed_sort_column = applicable_computed_sorts.attrib.get("column")
        applicable_computed_sort_column_components = tableau_documents.tableau_core_field_ref_to_components(applicable_computed_sort_column)
        applicable_computed_sort_column_agg = applicable_computed_sort_column_components.get("agg")
        applicable_computed_sort_column_name = applicable_computed_sort_column_components.get("name")
        applicable_computed_sort_using = applicable_computed_sorts.attrib.get("using")
        applicable_computed_sort_using_components = tableau_documents.tableau_core_field_ref_to_components(applicable_computed_sort_using)
        applicable_computed_sort_using_agg = applicable_computed_sort_using_components.get("agg")
        applicable_computed_sort_using_name = applicable_computed_sort_using_components.get("name")
        applicable_computed_sort_direction = applicable_computed_sorts.attrib.get("direction")
    else:
        return None

    return {
        "column": applicable_computed_sort_column,
        "column_agg": applicable_computed_sort_column_agg,
        "column_name": applicable_computed_sort_column_name,
        "using": applicable_computed_sort_using,
        "using_agg": applicable_computed_sort_using_agg,
        "using_name": applicable_computed_sort_using_name,
        "direction": applicable_computed_sort_direction
    }

def process_rows_or_cols_into_definition(sheet_definition:dict, fields_counter:int, selected_worksheet_elem: ET.Element, rows_or_cols:str, semantic_model_data_object:dict) -> Tuple[dict, int]:
    """
    Process the rows or columns of a worksheet into a definition format for a sheet/Visualization. Returns a tuple of the updated sheet definition and the updated fields counter.

    Arguments:
    - sheet_definition: The definition of the sheet being processed, from the template.
    - fields_counter: The current global count of fields being processed.
    - selected_worksheet_elem: The XML element representing the selected worksheet.
    - rows_or_cols: A string indicating whether to process rows or columns.
    - semantic_model_data_object: The semantic model data object containing (all) field information.
    """

    # We'd defined this in an upstream function already, but we didn't want to pass too many arguments...
    semantic_model_data_object_fields = semantic_model_data_object.get("semanticDimensions", []) + semantic_model_data_object.get("semanticMeasurements", [])

    rows_or_cols_for_next = "columns" if rows_or_cols == "cols" else "rows"
    
    worksheet_rc_fields = selected_worksheet_elem.find(f".//{ rows_or_cols }")
    worksheet_rc_fields_content = worksheet_rc_fields.text
    worksheet_rc_fields = worksheet_rc_fields_content.split(" / ")
    for rc_field in worksheet_rc_fields:
        # Core, XML
        rc_field_components = tableau_documents.tableau_core_field_ref_to_components(rc_field)
        rc_field_agg = rc_field_components.get("agg")
        rc_field_name = rc_field_components.get("name")
        # Find the sorts that apply to this field
        computed_sorts = get_computed_sort_from_xml(selected_worksheet_elem, field=rc_field)
        # Next, JSON/template
        fields_counter += 1
        fields_key = f"F{fields_counter}"
        sm_field_match = find_matching_field_in_semantic_model(rc_field_name, semantic_model_data_object)
        # Piece together the field definition
        field_definition = field_definition_from_semantic_model_field(sm_field_match, semantic_model_data_object, rc_field_agg)

        # Apply in our template/definition ...
        # In fields
        sheet_definition["fields"][fields_key] = field_definition
        # In rows/cols
        sheet_definition["visualSpecification"][rows_or_cols_for_next].append(fields_key)
        # In style/headers (if discrete)
        if field_definition["displayCategory"] == "Discrete":
            header_definition = copy.deepcopy(tableau_next_templates.visualization_visualspec_style_headers_template)
            sheet_definition["visualSpecification"]["style"]["headers"][fields_key] = header_definition
        # Axis
        if field_definition["displayCategory"] == "Continuous":
            axis_definition = copy.deepcopy(tableau_next_templates.visualization_visualspec_style_axis_template)
            sheet_definition["visualSpecification"]["style"]["axis"][fields_key] = axis_definition
        # Panes
        if field_definition["role"] == "Measure":
            pane_definition = copy.deepcopy(tableau_next_templates.visualization_visualspec_style_panes_template)
            sheet_definition["visualSpecification"]["style"]["panes"][fields_key] = pane_definition

        # Sort
        if computed_sorts is not None:
            fields_counter += 1
            fields_key_sort = f"F{fields_counter}"
            sm_match_for_sort = find_matching_field_in_semantic_model(computed_sorts.get("using_name"), semantic_model_data_object)
            sort_field_definition = field_definition_from_semantic_model_field(sm_match_for_sort, semantic_model_data_object, computed_sorts.get("using_agg"))
            # Add in fields ...
            sheet_definition["fields"][fields_key_sort] = sort_field_definition
            # ... and in viewSpecs -> sortOrders
            sheet_definition["view"]["viewSpecification"]["sortOrders"]["fields"][fields_key] = {
                "byField": fields_key_sort,
                "order": "Descending" if computed_sorts.get("direction", "DESC") == "DESC" else "Ascending",
                "type": "Field"
            }

    return sheet_definition, fields_counter

def process_marks_into_definition(sheet_definition:dict, fields_counter:int, selected_worksheet_elem: ET.Element, semantic_model_data_object:dict) -> Tuple[dict, int]:
    """
    Process the marks of a worksheet into a definition format for a sheet/Visualization. Returns a tuple of the updated sheet definition and the updated fields counter.

    Arguments:
    - sheet_definition: The definition of the sheet being processed, from the template.
    - fields_counter: The current global count of fields being processed.
    - selected_worksheet_elem: The XML element representing the selected worksheet.
    - semantic_model_data_object: The semantic model data object containing (all) field information.
    """

    # We'd defined this in an upstream function already, but we didn't want to pass too many arguments...
    semantic_model_data_object_fields = semantic_model_data_object.get("semanticDimensions", []) + semantic_model_data_object.get("semanticMeasurements", [])

    worksheet_marks_tag = selected_worksheet_elem.find(f".//mark")
    
    # Mark type
    marks_class = worksheet_marks_tag.attrib.get("class", None)
    try:
        # Convert "Automatic" to "Bar" for now
        marks_class = "Bar" if marks_class == "Automatic" else marks_class
        sheet_definition["visualSpecification"]["marks"]["ALL"]["type"] = marks_class
    except Exception as e:
        log_and_display_message(f"Error processing marks type:\n\t{ e }\n\t{ traceback.format_exc() }", level="warning")

    # Marks style rules
    marks_style_rule = selected_worksheet_elem.find(f".//style-rule[@element='mark']")
    try:
        marks_color = marks_style_rule.find(f".//format[@attr='mark-color']")
        # Single color (i.e. not encoded with a field)
        if marks_color is not None:
            marks_color_value = marks_color.attrib.get("value", "")
            if len(marks_color_value) > 0:
                sheet_definition["visualSpecification"]["style"]["marks"]["ALL"]["color"] = { "color": marks_color_value }
        # Color encoded with field
        else:
            marks_encodings = selected_worksheet_elem.find(f".//pane/encodings")
            if marks_encodings is not None:
                marks_encodings_color = marks_encodings.find(f".//color")
                if marks_encodings_color is not None:
                    marks_encodings_color_value = marks_encodings_color.attrib.get("column", "")
                    if len(marks_encodings_color_value) > 0:
                        # Interestingly, we don't need to set sheet_definition["visualSpecification"]["style"]["marks"]["ALL"]["color"]["color"]. Only add an encoding to sheet_definition["visualSpecification"]["marks"]["ALL"]["encodings"]
                        # Which field?
                        marks_encodings_color_components = tableau_documents.tableau_core_field_ref_to_components(marks_encodings_color_value)
                        marks_encodings_color_agg = marks_encodings_color_components.get("agg")
                        marks_encodings_color_name = marks_encodings_color_components.get("name")
                        # We need a field definition for that
                        fields_counter += 1
                        fields_key_color = f"F{fields_counter}"
                        sm_match_for_color = find_matching_field_in_semantic_model(marks_encodings_color_name, semantic_model_data_object)
                        color_field_definition = field_definition_from_semantic_model_field(sm_match_for_color, semantic_model_data_object, marks_encodings_color_agg)
                        # Add in fields ...
                        sheet_definition["fields"][fields_key_color] = color_field_definition
                        sheet_definition["visualSpecification"]["marks"]["ALL"]["encodings"].append({
                            "fieldKey": fields_key_color,
                            "type": "Color"
                        })
                        # Required if a measure: panes style.
                        if color_field_definition["role"] == "Measure":
                            pane_definition = copy.deepcopy(tableau_next_templates.visualization_visualspec_style_panes_template)
                            sheet_definition["visualSpecification"]["style"]["panes"][fields_key_color] = pane_definition
    except Exception as e:
        log_and_display_message(f"Error processing marks color:\n\t{ e }\n\t{ traceback.format_exc() }", level="warning")

    # Marks label (show, cull)
    try:
        marks_label = marks_style_rule.find(f".//format[@attr='mark-labels-show']")
        if marks_label is not None:
            marks_label_value = helpers_other.to_bool(marks_label.attrib.get("value", False))
            if marks_label_value:
                sheet_definition["visualSpecification"]["style"]["marks"]["ALL"]["label"]["showMarkLabels"] = marks_label_value 
        marks_label_cull = marks_style_rule.find(f".//format[@attr='mark-labels-cull']")
        if marks_label_cull is not None:
            marks_label_cull_value = helpers_other.to_bool(marks_label_cull.attrib.get("value", False))
            if marks_label_cull_value:
                sheet_definition["visualSpecification"]["style"]["marks"]["ALL"]["label"]["canOverlapLabels"] = marks_label_cull_value
    except Exception as e:
        log_and_display_message(f"Error processing marks label:\n\t{ e }\n\t{ traceback.format_exc() }", level="warning")

    # Extra: if mark-encodings was not None, and labels are displayed, we actually need to add that as an additional field in Tableau Next (we can't just display labels for a field that is dropped elsewhere)
    try:
        if marks_encodings is not None and marks_label is not None and marks_label_value:
            # The Fn+1 we add for label, will be a copy of the Fn for color. Do we have what we need?
            if "fields_key_color" in locals() and "color_field_definition" in locals() and color_field_definition is not None:
                # Create a copy of the color field definition for the label
                fields_counter += 1
                label_field_definition = copy.deepcopy(color_field_definition)
                sheet_definition["fields"][f"F{fields_counter}"] = label_field_definition
            # Then, also add to visualSpecification -> marks -> ALL -> encodings
            sheet_definition["visualSpecification"]["marks"]["ALL"]["encodings"].append({
                "fieldKey": f"F{fields_counter}",
                "type": "Label"
            })
            # Required if a measure: panes style.
            if label_field_definition["role"] == "Measure":
                pane_definition = copy.deepcopy(tableau_next_templates.visualization_visualspec_style_panes_template)
                sheet_definition["visualSpecification"]["style"]["panes"][f"F{fields_counter}"] = pane_definition
    except Exception as e:
        log_and_display_message(f"Error processing marks label encodings:\n\t{ e }\n\t{ traceback.format_exc() }", level="warning")

    return sheet_definition, fields_counter

def process_filters_into_definition(sheet_definition:dict, fields_counter:int, selected_worksheet_elem: ET.Element, semantic_model_data_object:dict) -> Tuple[dict, int]:
    """
    Process the filters of a worksheet into a definition format for a sheet/Visualization. Returns a tuple of the updated sheet definition and the updated fields counter.

    ! Currently only supports categorical filters with selection. !

    Arguments:
    - sheet_definition: The definition of the sheet being processed, from the template.
    - fields_counter: The current global count of fields being processed.
    - selected_worksheet_elem: The XML element representing the selected worksheet.
    - semantic_model_data_object: The semantic model data object containing field information.
    """

    # We'd defined this in an upstream function already, but we didn't want to pass too many arguments...
    semantic_model_data_object_fields = semantic_model_data_object.get("semanticDimensions", []) + semantic_model_data_object.get("semanticMeasurements", [])

    worksheet_filter_tags = selected_worksheet_elem.findall(f".//filter")
    for filter_tag in worksheet_filter_tags:

        try:
            # Filter field
            filter_class = filter_tag.attrib.get("class", None)
            filter_column = filter_tag.attrib.get("column", None)
            filter_column_components = tableau_documents.tableau_core_field_ref_to_components(filter_column)

            if filter_class == "categorical":

                sm_field_match = find_matching_field_in_semantic_model(filter_column_components.get("name"), semantic_model_data_object)
                # Piece together and add the field definition
                field_definition = field_definition_from_semantic_model_field(sm_field_match, semantic_model_data_object, filter_column_components.get("agg"))
                fields_counter += 1
                filter_field_key = f"F{fields_counter}"
                sheet_definition["fields"][filter_field_key] = field_definition

                # Determine specifications. For a single selection, there is a single groupfilter tag with function "member" in the filter. For multiple selections, there is one child groupfilter tag with function union, which in turn has n groupfilter children, each representing a selected item.
                filter_groupfilter_tags = filter_tag.findall(f".//groupfilter")
                # Common (single/multiple) attributes
                filter_tag_enumeration = filter_tag.attrib.get("user:ui-enumeration", "inclusive")
                filter_selected_members = []
                # Single selection, "member"
                if len(filter_groupfilter_tags) == 1:
                    # Single selection
                    groupfilter = filter_groupfilter_tags[0]
                    if groupfilter.attrib.get("function") == "member":
                        selected_member = groupfilter.attrib.get("member", "").replace("&quot;", "").replace('"', "") # Tableau Next does not do HTML-encoded quotes in XML
                        filter_selected_members.append(selected_member)
                # Multiple selections, "union"
                elif len(filter_groupfilter_tags) > 1:
                    # Multiple selections
                    union_groupfilter = next((gf for gf in filter_groupfilter_tags if gf.attrib.get("function") == "union"), None)
                    member_groupfilters = [gf for gf in filter_groupfilter_tags if gf.attrib.get("function") == "member"]
                    for member_groupfilter in member_groupfilters:
                        selected_member = member_groupfilter.attrib.get("member", "").replace("&quot;", "").replace('"', "")
                        filter_selected_members.append(selected_member)

                # Add this info to the definition's filters
                filter_definition = copy.deepcopy(tableau_next_templates.visualization_filter_template)
                filter_definition["fieldKey"] = filter_field_key
                filter_definition["isContext"] = False
                filter_definition_filter_infos = {
                    "isCustom": False,
                    "isExcludes": filter_tag_enumeration != "inclusive",
                    "type": "In",
                    "useAll": False,
                    "values": filter_selected_members
                }
                filter_definition["filterInfos"].append(filter_definition_filter_infos)
                sheet_definition["view"]["viewSpecification"]["filters"].append(filter_definition)

            else:
                log_and_display_message(f"Skipping filter of class '{ filter_class }' on column '{ filter_column }' as it is not supported yet.", level="warning")

        except Exception as e:
            log_and_display_message(f"Error processing filters  :\n\t{ e }\n\t{ traceback.format_exc() }", level="warning")

    return sheet_definition, fields_counter

def process_other_into_definition(sheet_definition:dict, fields_counter:int, selected_worksheet_elem: ET.Element, tableau_core_workbook_tree: ET.Element, semantic_model_data_object:dict) -> Tuple[dict, int]:
    """
    Process a worksheet's additional properties into a definition format for a sheet/Visualization. Returns a tuple of the updated sheet definition and the updated fields counter.

    Arguments:
    - sheet_definition: The definition of the sheet being processed, from the template.
    - fields_counter: The current global count of fields being processed.
    - selected_worksheet_elem: The XML element representing the selected worksheet.
    - tableau_core_workbook_tree: The XML element representing the full workbook, as we look up stuff in other places than just the worksheet tag here.
    - semantic_model_data_object: The semantic model data object containing (all) field information.
    """

    # Find the window tag for this worksheet
    tableau_core_dashboard_windows = tableau_core_workbook_tree.findall(".//window")
    worksheet_window_elem = [w for w in tableau_core_dashboard_windows if w.attrib.get("class", "?") == "worksheet" and w.attrib.get("name", "!").lower() == selected_worksheet_elem.attrib.get("name", "?").lower()][0]

    # We'd defined this in an upstream function already, but we didn't want to pass too many arguments...
    semantic_model_data_object_fields = semantic_model_data_object.get("semanticDimensions", []) + semantic_model_data_object.get("semanticMeasurements", [])

    # View fit (entire view, fit width, height, normal)
    try:
        viewpoint_zoom_tag = worksheet_window_elem.find(f".//viewpoint/zoom")
        if viewpoint_zoom_tag is not None:
            viewpoint_zoom_type = viewpoint_zoom_tag.attrib.get("type", None)
            if viewpoint_zoom_type is not None:
                viewpoint_zoom_type = viewpoint_zoom_core_to_next.get(viewpoint_zoom_type, viewpoint_zoom_type)
                sheet_definition["visualSpecification"]["style"]["fit"] = viewpoint_zoom_type
    except Exception as e:
        log_and_display_message(f"Error processing window viewpoint zoom type:\n\t{ e }\n\t{ traceback.format_exc() }", level="warning")

    return sheet_definition, fields_counter



# Experiments

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
