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
                "columns": {
                    "showLabels": True,
                    "showDividerLine": False
                },
                "rows": {
                    "showLabels": True,
                    "showDividerLine": False
                },
            },
            "fit": "Standard",
            "allHeaders": {
                "fields": {},
                "columns": {
                    "mergeRepeatedCells": True,
                    "showIndex": False
                },
                "rows": {
                    "mergeRepeatedCells": True,
                    "showIndex": False
                }
            },
            "marks": {
                "ALL": {
                    "color": {
                        "color": ""
                    },
                    "isAutomaticSize": True,
                    "size": {
                        "isAutomatic": True,
                        "type": "Percentage",
                        "value": 75
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
            "lines": {
                "axisLine": {
                    "color": "#C9C9C9"
                },
                "fieldLabelDividerLine": {
                    "color": "#C9C9C9"
                },
                "separatorLine": {
                    "color": "#C9C9C9"
                },
                "zeroLine": {
                    "color": "#C9C9C9"
                }
            },
            "panes": {},
            "shading": {
                "backgroundColor": "#FFFFFF",
                "banding": {
                    "rows": {
                        "color": "#E5E5E5"
                    }
                }
            },
            "fonts": {
                "actionableHeaders": {
                    "color": "#0250D9",
                    "size": 13
                },
                "axisTickLabels": {
                    "color": "#2E2E2E",
                    "size": 13
                },
                "fieldLabels": {
                    "color": "#2E2E2E",
                    "size": 13
                },
                "headers": {
                    "color": "#2E2E2E",
                    "size": 13
                },
                "legendLabels": {
                    "color": "#2E2E2E",
                    "size": 13
                },
                "markLabels": {
                    "color": "#2E2E2E",
                    "size": 13
                },
                "marks": {
                    "color": "#2E2E2E",
                    "size": 13
                }
            },
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
