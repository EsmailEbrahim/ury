import frappe


def before_insert(doc, method):
    sales_invoice_naming(doc, method)


def sales_invoice_naming(doc, method):
    pos_profile = frappe.db.get_value("POS Profile", doc.pos_profile, ["restaurant_prefix", "restaurant"], as_dict=True)
    restaurant = pos_profile.get("restaurant")
    
    
    if pos_profile.get("restaurant_prefix") == 1 and restaurant:
                
        if doc.order_type == "Aggregators":
            doc.naming_series = "SINV-" + frappe.db.get_value(
            "URY Restaurant", restaurant, "aggregator_series_prefix")
            
            if frappe.db.get_value("Branch", doc.branch , "custom_make_unpaid") == 1:
                doc.is_pos = 0
        
        else:
            
            doc.naming_series = "SINV-" + frappe.db.get_value(
                "URY Restaurant", restaurant, "invoice_series_prefix"
            )
            

