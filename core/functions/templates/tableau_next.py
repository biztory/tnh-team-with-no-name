visualization_template = {
    "dataSource": {
        "id": "2SMNS000001DV734AG",
        "type": "SemanticModel",
    },
    "fields": {},
    "interactions": [],
    "label": "",
    "view": {
        "label": "",
        "name": "",
        "viewSpecification": {
            "filters": [],
            "sortOrders": {
                "columns": [],
                "fields": {},
                "rows": [],
            },
        },
    },
    "visualSpecification": {
        "columns": [],
        "rows": [],
        "forecasts": {},
        "legends": {},
        "marks": {
            "ALL": {
                "encodings": [],
                "isAutomatic": True,
                "stack": {
                    "isAutomatic": True,
                    "isStacked": True
                },
                "type": "Bar",
            }
        },
        "measureValues": [],
        "mode": "Visualization",
        "referenceLines": {},
        "style": {
            "axis": {},
            "fieldLabels": {
                "columns": {"showLabels": True},
                "rows": {"showLabels": True},
            },
            "fit": "Standard",
            "headers": {},
            "marks": {
                "ALL": {
                    "color": {
                        "color": ""
                    },
                    "label": {
                        "canOverlapLabels": False,
                        "marksToLabel": {
                            "type": "All"
                        },
                        "showMarkLabels": False,
                    },
                    "range": {
                        "reverse": True
                    },
                }
            },
            "panes": {},
            "referenceLines": {},
            "showDataPlaceholder": False,
            "title": {"isVisible": True},
        },
    },
}

# Added to view -> viewSpecification -> filters as { "fieldKey": "Fn", "filterInfos": [...], "isContext": ... }
visualization_filter_template = {
    "fieldKey": "",
    "filterInfos": [],
    "isContext": False,
}

# Uses a field reference as key e.g. "F1" = {...}
visualization_field_template = {
    "displayCategory": "Discrete",
    "fieldName": "team_member_name",
    "objectName": "Biztory_Strava_Data",
    "role": "Dimension",
    "type": "Field",
}

# Uses a field reference as key e.g. "F4" = {...}
visualization_sortorder_fields_template = {
    "byField": "F4",
    "order": "Descending",
    "type": "Field",
}

# Uses a field reference as key e.g. "F4" = {...}
visualization_visualspec_style_axis_template = {
    "isVisible": True,
    "range": {"includeZero": True, "type": "Auto"},
    "scale": {
        "format": {
            "numberFormatInfo": {
                "decimalPlaces": 2,
                "displayUnits": "Auto",
                "includeThousandSeparator": True,
                "negativeValuesFormat": "Auto",
                "prefix": "",
                "suffix": "",
                "type": "NumberShort",
            }
        }
    },
    "ticks": {
        "majorTicks": {"type": "Auto"},
        "minorTicks": {"type": "Auto"},
    },
}

# Uses a field reference as key e.g. "F4" = {...}
visualization_visualspec_style_headers_template = {
    "hiddenValues": [],
    "isVisible": True,
    "showMissingValues": False,
}

# Uses a field reference as key e.g. "F4" = {...}
visualization_visualspec_style_panes_template = {
    "defaults": {
        "format": {
            "numberFormatInfo": {
                "decimalPlaces": 2,
                "displayUnits": "Auto",
                "includeThousandSeparator": True,
                "negativeValuesFormat": "Auto",
                "prefix": "",
                "suffix": "",
                "type": "Number",
            }
        }
    }
}
