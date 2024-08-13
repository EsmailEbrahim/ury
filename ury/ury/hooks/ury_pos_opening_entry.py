import frappe

def validate(doc,method):
    set_cashier_room(doc,method)
    
    
    
def set_cashier_room(doc,method):
    room =  frappe.db.sql("""
                SELECT room , parent
                FROM `tabURY User`
                WHERE parent=%s AND user=%s         
            """,(doc.branch,doc.user),as_dict=True)
    
    if room:
        # If there's a result, fetch the custom_room value
        doc.custom_room = room[0]['room']