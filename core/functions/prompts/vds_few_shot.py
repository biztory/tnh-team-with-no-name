few_shot = {
    "Examples for fields": {
        "Example 1": {
            "Question": "Show me sales by segment",
            "VDS Query": {
                "fields": [
                {"fieldCaption": "Segment"},
                {"fieldCaption": "Sales", "function": "SUM", "maxDecimalPlaces": 2}
            ]
            },
        },
        "Example 2": {
            "Question": "What are the total sales and profit for each product category?",
            "VDS Query": {
                "fields": [
                    {"fieldCaption": "Category"},
                    {"fieldCaption": "Sales", "function": "SUM", "maxDecimalPlaces": 2},
                    {"fieldCaption": "Profit", "function": "SUM", "maxDecimalPlaces": 2}
                ]
            },
        },
        "Example 3": {
            "Question": "Display the number of orders by ship mode",
            "VDS Query": {
                "fields": [
                    {"fieldCaption": "Ship Mode"},
                    {"fieldCaption": "Order ID", "function": "COUNT", "columnAlias": "Number of Orders"}
                ]
            },
        },
        "Example 4": {
            "Question": "Show me the average sales per customer by segment",
            "VDS Query": {
                "fields": [
                    {"fieldCaption": "Segment"},
                    {"fieldCaption": "Sales", "function": "AVG", "maxDecimalPlaces": 2, "columnAlias": "Average Sales per Customer"}
                ]
            },
        },
        "Example 5": {
            "Question": "What are the total sales for each state or province?",
            "VDS Query": {
                "fields": [
                    {"fieldCaption": "State/Province"},
                    {"fieldCaption": "Sales", "function": "SUM", "maxDecimalPlaces": 2}
                ]
            },
        },
    },
    "Examples for filters": {
        "Example 1": {
            "Question": "Show me sales for the top 10 cities",
            "VDS Query": {
                "fields": [
                    {"fieldCaption": "City"},
                    {"fieldCaption": "Sales", "function": "SUM", "maxDecimalPlaces": 2}
                ],
                "filters": [
                    {
                        "field": { "fieldCaption": "City" },
                        "filterType": "TOP",
                        "direction": "TOP",
                        "howMany": 10,
                        "fieldToMeasure": { "field": { "fieldCaption": "Sales" }, "function": "SUM" }
                    }
                ]
            }
        },
        "Example 2": {
            "Question": "What are the sales for furniture products in the last 6 months?",
            "VDS Query": {
                "fields": [
                    {"fieldCaption": "Product Name"},
                    {"fieldCaption": "Sales", "function": "SUM", "maxDecimalPlaces": 2}
                ],
                "filters": [
                    {
                        "field": { "fieldCaption": "Category" },
                        "filterType": "SET",
                        "values": ["Furniture"],
                        "exclude": False
                    },
                    {
                        "field": { "fieldCaption": "Order Date" },
                        "filterType": "DATE",
                        "periodType": "MONTHS",
                        "dateRangeType": "LASTN",
                        "rangeN": 6
                    }
                ]
            }
        },
        "Example 3": {
            "Question": "List customers who have made purchases over $1000 in the Consumer segment",
            "VDS Query": {
                "fields": [
                    {"fieldCaption": "Customer Name"},
                    {"fieldCaption": "Sales", "function": "SUM", "maxDecimalPlaces": 2}
                ],
                "filters": [
                    {
                        "field": { "fieldCaption": "Sales" },
                        "filterType": "QUANTITATIVE_NUMERICAL",
                        "quantitativeFilterType": "MIN",
                        "min": 1000
                    },
                    {
                        "field": { "fieldCaption": "Segment" },
                        "filterType": "SET",
                        "values": ["Consumer"],
                        "exclude": False
                    }
                ]
            }
        },
        "Example 4": {
            "Question": "Show me the orders that were returned in the West region",
            "VDS Query": {
                "fields": [
                    {"fieldCaption": "Order ID"},
                    {"fieldCaption": "Product Name"},
                    {"fieldCaption": "Sales", "function": "SUM", "maxDecimalPlaces": 2}
                ],
                "filters": [
                    {
                        "field": { "fieldCaption": "Returned" },
                        "filterType": "SET",
                        "values": [True],
                        "exclude": False
                    },
                    {
                        "field": { "fieldCaption": "Region" },
                        "filterType": "SET",
                        "values": ["West"],
                        "exclude": False
                    }
                ]
            }
        },
        "Example 5": {
            "Question": "What are the top 5 sub-categories by sales, excluding the Technology category?",
            "VDS Query": {
                "fields": [
                    {"fieldCaption": "Sub-Category"},
                    {"fieldCaption": "Sales", "function": "SUM", "maxDecimalPlaces": 2}
                ],
                "filters": [
                    {
                        "field": { "fieldCaption": "Category" },
                        "filterType": "SET",
                        "values": ["Technology"],
                        "exclude": True,
                    },
                    {
                        "field": { "fieldCaption": "Sales" },
                        "filterType": "TOP",
                        "direction": "TOP",
                        "howMany": 5,
                        "fieldToMeasure": {"field": { "fieldCaption": "Sales", "function": "SUM"} }
                    }
                ]
            }
        },
        "Example 6": {
            "Question": "Top selling sub-categories with a minimum of $200,000",
            "VDS Query": {
                "fields": [
                    {"fieldCaption": "Sub-Category"},
                    {"fieldCaption": "Sales", "function": "SUM"}
                ],
                "filters": [
                    { 
                        "field": { "fieldCaption": "Sales", "function": "SUM" }, 
                        "filterType": "QUANTITATIVE_NUMERICAL", "quantitativeFilterType": "MIN", "min": 200000
                    }
                ]
            }
        }
    }
}