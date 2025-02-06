import frappe
from frappe.utils.password import check_password


@frappe.whitelist()
def validate_manager(username, password, pos_profile):
    try:
        user = frappe.get_doc("User", username)
        
        roles_allowed_for_voiding = frappe.get_all(
            "Role Permitted",
            filters={
                "parent": pos_profile,
                "parentfield": "custom_roles_allowed_for_voiding",
                "parenttype": "POS Profile"
            },
            fields=["role"]
        )
        
        roles_allowed_for_voiding_list = [role["role"] for role in roles_allowed_for_voiding]

        user_roles = [role.role for role in user.get("roles")]
        if not any(role in roles_allowed_for_voiding_list for role in user_roles):
            return {"success": False, "message": "المستخدم ليس لديه صلاحيات."}

        check_password(user=user.name, pwd=password)
        
        return {"success": True}

    except frappe.DoesNotExistError:
        return {"success": False, "message": "المستخدم غير موجود."}
    except frappe.AuthenticationError:
        return {"success": False, "message": "خطأ في اسم المستخدم أو كلمة المرور."}
    except Exception as e:
        frappe.log_error(message=str(e), title="Manager Validation Error")
        return {"success": False, "message": "حدث خطأ غير متوقع في التحقق من المستخدم."}


@frappe.whitelist()
def process_void_item(invoice_no, items, accountability, notes, username, password, pos_profile, session_user):
    try:
        user_allowed = validate_manager(username, password, pos_profile)
        
        if user_allowed['success'] == True:
            invoice = frappe.get_doc("POS Invoice", invoice_no)

            if invoice.docstatus == 0:
                for index, item in enumerate(items, start=1):
                    if item['item'] == None or item['quantity'] == None:
                        return {"success": False, "message": f"الرجاء اختيار العنصر والكمية في الصف: { index }"}

                    current_item = item['item']
                    current_quantity = item['quantity']
                    voided_item = {
                        "item": current_item['item'],
                        "rate": current_item['rate'],
                        "quantity": current_quantity,
                        "amount": current_item['rate'] * current_quantity,
                        "accountability": accountability,
                        "notes": notes,
                        "voided_by": username,
                        "session_user": session_user,
                    }
                    invoice.append("custom_voided_items", voided_item)
                
                invoice.save()
                return {"success": True}
            else:
                return {"success": False, "message": f"لا يمكن إتلاف أي عنصر من هذه الفاتورة (حالة الفاتورة: {invoice.status})."}
        else:
            return user_allowed

    except Exception as e:
        return {"success": False, "message": "حدث خطأ غير متوقع في  معالجة الإتلاف. رسالة الخطأ: " + str(e)}
