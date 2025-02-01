import frappe
from frappe import _
from datetime import date, datetime, timedelta
from frappe.utils import now_datetime


@frappe.whitelist()
def get_user_roles(user=None):
    # Use logged-in user if no user is specified
    if not user:
        user = frappe.session.user

    # Get the roles of the specified user
    roles = frappe.get_roles(user)
    
    return roles


@frappe.whitelist()
def get_table_invoice(table):
    """returns the active invoice linked to the given table"""

    if table:
        invoice_name = frappe.get_value(
            "POS Invoice",
            dict(restaurant_table=table, docstatus=0, invoice_printed=0),
            ['name', 'custom_is_confirmed']
        )

        return invoice_name


@frappe.whitelist()
def getTable(room):
    branch_name = getBranch()   
    tables = frappe.get_all(
        "URY Table",
        fields=["name", "occupied", "latest_invoice_time", "is_take_away", "restaurant_room"],
        filters={"branch": branch_name,"restaurant_room":room,}
    )

    for table in tables:
        table_invoice = get_table_invoice(table.name)
        if table_invoice:
            table.table_invoice = table_invoice[0]
            table.custom_is_confirmed = table_invoice[1]
        else:
            table.table_invoice = None
            table.custom_is_confirmed = 0

    return tables


#########################################################################################
@frappe.whitelist()
def get_order_status(table, invoice):
    if not table or not invoice:
        frappe.throw("Both 'table' and 'invoice' parameters are required.")

    orders = frappe.get_all(
        "URY KOT",
        filters={"restaurant_table": table, "invoice": invoice},
        fields=[
            "name",
            "order_status",
            "restaurant_table",
            "invoice",
            "preparation_time",
            "start_time_prep",
            "date",
            "type"
        ]
    )

    if not orders:
        return {"error": "No matching orders found"}

    result = []
    for order in orders:
        start_time_prep = order.get("start_time_prep")
        elapsed_time = 0
        remaining_time = 0

        if start_time_prep:
            full_start_time = f"{order.get('date')} {start_time_prep}"
            try:
                start_time_prep = frappe.utils.get_datetime(full_start_time)
            except Exception as e:
                frappe.log_error(f"Error parsing datetime: {e}")
                start_time_prep = None

            if isinstance(start_time_prep, datetime):
                now = frappe.utils.now_datetime()
                delta = now - start_time_prep
                elapsed_time = delta.total_seconds() / 60
                remaining_time = max(order.get("preparation_time", 0) - elapsed_time, 0)

        kot_items = frappe.get_all(
            "URY KOT Items",
            filters={"parent": order["name"]},
            fields=["item_name", "quantity", "preparation_time", "striked"]
        )

        all_items_ready = True
        items_details = []

        for item in kot_items:
            is_ready = item.get("striked", 0) == 1
            if not is_ready:
                all_items_ready = False
            items_details.append({
                "item_name": item.get("item_name"),
                "quantity": item.get("quantity"),
                "preparation_time": item.get("preparation_time"),
                "is_ready": is_ready,
            })

        overall_status = "Served" if all_items_ready else order.get("order_status")

        result.append({
            "order_id": order["name"],
            "table": order["restaurant_table"],
            "invoice": order["invoice"],
            "elapsed_time": round(elapsed_time, 2),
            "remaining_time": round(remaining_time, 2),
            "order_status": overall_status,
            "items": items_details,
            "type": order["type"]
        })

    return result
#########################################################################################


@frappe.whitelist()
def getRestaurantMenu(pos_profile, table=None):
    menu_items = []
    menu_items_with_image = []

    user_role = frappe.get_roles()

    pos_profile = frappe.get_doc("POS Profile", pos_profile)

    cashier = any(
        role.role in user_role for role in pos_profile.role_allowed_for_billing
    )

    if cashier:
        branch_name = getBranch()
        menu = frappe.db.get_value(
            "URY Restaurant", {"branch": branch_name}, "active_menu"
        )

        if menu:
            menu_items = frappe.get_all(
                "URY Menu Item",
                filters={"parent": menu},
                fields=["item", "item_name", "rate", "special_dish", "disabled","course", "preparation_time", "parallel_preparation"],
                order_by="item_name asc",
            )

            menu_items_with_image = [
                {
                    "item": item.item,
                    "item_name": item.item_name,
                    "rate": item.rate,
                    "special_dish": item.special_dish,
                    "disabled": item.disabled,
                    "item_imgae": frappe.db.get_value("Item", item.item, "image"),
                    "course":item.course,
                    "preparation_time": item.preparation_time,
                    "parallel_preparation": item.parallel_preparation,
                }
                for item in menu_items
            ]

    elif table:
        if not table:
            frappe.throw(_("Please select a table"))

        restaurant, branch, room = frappe.get_value(
            "URY Table",
            table,
            ["restaurant", "branch", "restaurant_room"],
        )

        room_wise_menu = frappe.db.get_value(
            "URY Restaurant",
            restaurant,
            "room_wise_menu",
        )

        if not room_wise_menu:
            menu = frappe.db.get_value("URY Restaurant", restaurant, "active_menu")

        else:
            menu = frappe.db.get_value(
                "Menu for Room",
                {"parent": restaurant, "room": room},
                "menu",
            )

        if not menu:
            frappe.throw(
                _("Please set an active menu for Restaurant {0}").format(restaurant)
            )

        else:
            menu_items = frappe.get_all(
                "URY Menu Item",
                filters={"parent": menu},
                fields=["item", "item_name", "rate", "special_dish", "disabled", "course", "preparation_time", "parallel_preparation"],
                order_by="item_name asc",
            )
            menu_items_with_image = [
                {
                    "item": item.item,
                    "item_name": item.item_name,
                    "rate": item.rate,
                    "special_dish": item.special_dish,
                    "disabled": item.disabled,
                    "item_imgae": frappe.db.get_value("Item", item.item, "image"),
                    "course":item.course,
                    "preparation_time": item.preparation_time,
                    "parallel_preparation": item.parallel_preparation,
                }
                for item in menu_items
            ]
    return menu_items_with_image


@frappe.whitelist()
def getBranch():
    user = frappe.session.user
    if user != "Administrator":
        sql_query = """
            SELECT b.branch
            FROM `tabURY User` AS a
            INNER JOIN `tabBranch` AS b ON a.parent = b.name
            WHERE a.user = %s
        """
        branch_array = frappe.db.sql(sql_query, user, as_dict=True)
        if not branch_array:
            frappe.throw("User is not Associated with any Branch.Please refresh Page")

        branch_name = branch_array[0].get("branch")

        return branch_name

@frappe.whitelist()
def getBranchRoom():
    user = frappe.session.user
    if user != "Administrator":
        sql_query = """
            SELECT b.branch , a.room
            FROM `tabURY User` AS a
            INNER JOIN `tabBranch` AS b ON a.parent = b.name
            WHERE a.user = %s
        """
        branch_array = frappe.db.sql(sql_query, user, as_dict=True)
        
        branch_name = branch_array[0].get("branch")
        room_name = branch_array[0].get("room")
    
        if not branch_name:
            frappe.throw("Branch information is missing for the user. Please contact your administrator.")

        if not room_name:
            frappe.throw("No room assigned to this user. Please contact your administrator.")

        return branch_name,room_name


@frappe.whitelist()
def getModeOfPayment():
    posDetails = getPosProfile()
    posProfile = posDetails["pos_profile"]
    posProfiles = frappe.get_doc("POS Profile", posProfile)
    mode_of_payments = posProfiles.payments
    modeOfPayments = []
    for mop in mode_of_payments:
        modeOfPayments.append(
            {"mode_of_payment": mop.mode_of_payment, "opening_amount": float(0)}
        )
    return modeOfPayments


@frappe.whitelist()
def getPosInvoice(status, limit, limit_start):
    branch = getBranch()
    updatedlist = []
    limit = int(limit)+1
    limit_start = int(limit_start)
    if status == "Draft":
        invoices = frappe.db.sql(
            """
            SELECT 
                name, invoice_printed, grand_total, restaurant_table, 
                cashier, waiter, net_total, posting_time, 
                total_taxes_and_charges, customer, status, 
                posting_date, rounded_total, order_type 
            FROM `tabPOS Invoice` 
            WHERE branch = %s AND status = %s 
            AND (invoice_printed = 1 OR (invoice_printed = 0 AND COALESCE(restaurant_table, '') = ''))
            ORDER BY modified desc
            LIMIT %s OFFSET %s
            """,
            (branch, status, limit,limit_start),
            as_dict=True,
        )
        updatedlist.extend(invoices)
    elif status == "Unconfirmed":
        docstatus = "Draft"
        invoices = frappe.db.sql(
            """
            SELECT 
                name, invoice_printed, custom_is_confirmed, grand_total, restaurant_table, 
                cashier, waiter, net_total, posting_time, 
                total_taxes_and_charges, customer, status, 
                posting_date, rounded_total, order_type 
            FROM `tabPOS Invoice` 
            WHERE branch = %s AND status = %s 
            AND (invoice_printed = 0 AND restaurant_table IS NOT NULL AND custom_is_confirmed = 0)
            ORDER BY modified desc
            LIMIT %s OFFSET %s
            """,
            (branch, docstatus, limit, limit_start),
            as_dict=True,
        )
        updatedlist.extend(invoices)
    elif status == "Unbilled":
        docstatus = "Draft"
        invoices = frappe.db.sql(
            """
            SELECT 
                name, invoice_printed, custom_is_confirmed, grand_total, restaurant_table, 
                cashier, waiter, net_total, posting_time, 
                total_taxes_and_charges, customer, status, 
                posting_date, rounded_total, order_type 
            FROM `tabPOS Invoice` 
            WHERE branch = %s AND status = %s 
            AND (invoice_printed = 0 AND restaurant_table IS NOT NULL AND custom_is_confirmed = 1)
            ORDER BY modified desc
            LIMIT %s OFFSET %s
            """,
            (branch, docstatus, limit, limit_start),
            as_dict=True,
        )
        updatedlist.extend(invoices)
    elif status == "Recently Paid":
        docstatus = "Paid"
        invoices = frappe.db.sql(
            """
            SELECT 
                name, invoice_printed, grand_total, restaurant_table, 
                cashier, waiter, net_total, posting_time, 
                total_taxes_and_charges, customer, status, 
                posting_date, rounded_total, order_type 
            FROM `tabPOS Invoice` 
            WHERE branch = %s AND status = %s 
            ORDER BY modified desc
            LIMIT %s OFFSET %s
            """,
            (branch, docstatus, limit, limit_start),
            as_dict=True,
        )
        updatedlist.extend(invoices)    
    else:
        
        invoices = frappe.db.sql(
            """
            SELECT 
                name, invoice_printed, grand_total, restaurant_table, 
                cashier, waiter, net_total, posting_time, 
                total_taxes_and_charges, customer, status, 
                posting_date, rounded_total, order_type 
            FROM `tabPOS Invoice` 
            WHERE branch = %s AND status = %s 
            ORDER BY modified desc
            LIMIT %s OFFSET %s
            """,
            (branch, status, limit, limit_start),
            as_dict=True,
        )

        updatedlist.extend(invoices)
    if len(updatedlist) == limit and status != "Recently Paid":
            next = True
            updatedlist.pop()
    else:
            next = False   
    return  { "data":updatedlist,"next":next}


@frappe.whitelist()
def get_select_field_options():
    # options = frappe.get_meta("POS Invoice").get_field("order_type").options
    # if options:
    #     return [{"name": option} for option in options.split("\n")]
    # else:
    #     return []
    order_types = frappe.get_all(
        "URY Order Type",
        fields=["name", "order_type_arabic", "require_a_table", "default", "default_table"],
        filters={'disabled': 0}
    )
    
    return [
        {
            "name": order_type.name,
            "name_arabic": order_type.order_type_arabic,
            "require_a_table": order_type.require_a_table,
            "default": order_type.default,
            "default_table": order_type.default_table
        }
        for order_type in order_types
    ]


@frappe.whitelist()
def selectedOrderTypeRequireTable(type):
    require_a_table = frappe.db.get_value(
        "URY Order Type",
        type,
        "require_a_table"
    )
    
    return require_a_table


@frappe.whitelist()
def getDefaultTableForOrderType(type):
    default_table = frappe.db.get_value(
        "URY Order Type",
        type,
        "default_table"
    )
    
    return default_table


@frappe.whitelist()
def fav_items(customer):
    pos_invoices = frappe.get_all(
        "POS Invoice", filters={"customer": customer}, fields=["name"]
    )
    item_qty = {}

    for invoice in pos_invoices:
        pos_invoice = frappe.get_doc("POS Invoice", invoice.name)
        for item in pos_invoice.items:
            item_name = item.item_name
            qty = item.qty
            if item_name not in item_qty:
                item_qty[item_name] = 0
            item_qty[item_name] += qty

    favorite_items = [
        {"item_name": item_name, "qty": qty} for item_name, qty in item_qty.items()
    ]
    return favorite_items


@frappe.whitelist()
def getRestaurantName():
    branchName = getBranch()
    posProfile = frappe.db.exists("POS Profile", {"branch": branchName})
    pos_profile_restaurant_name = frappe.db.get_value("POS Profile", posProfile, "restaurant")
    pos_profile_restaurant_image = frappe.db.get_value("URY Restaurant", pos_profile_restaurant_name, "image")

    return {"name": pos_profile_restaurant_name, "image": pos_profile_restaurant_image}


@frappe.whitelist()
def getDefaultCustomer():
    branchName = getBranch()
    posProfile = frappe.db.exists("POS Profile", {"branch": branchName})
    pos_profile_customer = frappe.db.get_value("POS Profile", posProfile, "customer")

    return {'default_customer': pos_profile_customer}


@frappe.whitelist(allow_guest=True) # Remove the allow_guest
def getRestaurantSystemSettings():
    restaurant_system_settings = frappe.get_single("Restaurant System Settings")
    return restaurant_system_settings.as_dict()


@frappe.whitelist()
def get_cashier_printer_name_from_pos_profile(pos_profile):
    user = frappe.session.user
    if user != "Administrator":
        # SQL query to get the cashier printer name
        sql_query = """
            SELECT a.custom_cashier_printer_name, a.custom_cashier_qz_host
            FROM `tabPOS Profile User` AS a
            WHERE a.user = %s
              AND a.parenttype = 'POS Profile'
              AND a.parentfield = 'applicable_for_users'
              AND a.parent = %s
        """
        printer_array = frappe.db.sql(sql_query, (user, pos_profile), as_dict=True)
        
        if not printer_array:
            frappe.throw("User is not associated with any printer in the specified POS Profile.")

        # Return the first match, as there should be one printer per user per POS Profile
        cashier_printer_name = printer_array[0].get("custom_cashier_printer_name")
        cashier_qz_host = printer_array[0].get("custom_cashier_qz_host")

        qz_data = {'custom_cashier_printer_name': cashier_printer_name, 'custom_cashier_qz_host': cashier_qz_host}
        
        return qz_data


@frappe.whitelist()
def get_cashier_silent_print_format_from_pos_profile(pos_profile):
    user = frappe.session.user
    if user != "Administrator":
        # SQL query to get the cashier silent print format
        sql_query = """
            SELECT a.custom_silent_print_format, a.custom_silent_print_type
            FROM `tabPOS Profile User` AS a
            WHERE a.user = %s
              AND a.parenttype = 'POS Profile'
              AND a.parentfield = 'applicable_for_users'
              AND a.parent = %s
        """
        printer_array = frappe.db.sql(sql_query, (user, pos_profile), as_dict=True)
        
        if not printer_array:
            frappe.throw("User is not associated with any printer in the specified POS Profile.")

        # Return the first match, as there should be one printer per user per POS Profile
        silent_print_format = printer_array[0].get("custom_silent_print_format")
        silent_print_type = printer_array[0].get("custom_silent_print_type")

        silent_print_data = {'custom_silent_print_format': silent_print_format, "custom_silent_print_type": silent_print_type}
        
        return silent_print_data


@frappe.whitelist()
def get_ury_kot_by_invoice_number(invoice_number, type=None):
    filters = {'invoice': invoice_number}

    if type:
        filters['type'] = type
    
    ury_kots = frappe.get_all(
        'URY KOT',
        filters = filters,
        fields=['name', 'invoice', 'production', 'type'],
    )

    kitchen_controller_roles = []

    for ury_kot in ury_kots:
        production_silent_print_format = frappe.db.get_value('URY Production Unit', ury_kot['production'], 'silent_print_format')
        production_silent_print_type = frappe.db.get_value('URY Production Unit', ury_kot['production'], 'silent_print_type')
        kitchen_controller_roles.append(frappe.db.get_value('URY Production Unit', ury_kot['production'], 'role_responsible_for_serving_kot'))
        
        if production_silent_print_format and production_silent_print_type:
            ury_kot['production_silent_print_format'] = production_silent_print_format
            ury_kot['production_silent_print_type'] = production_silent_print_type
        else:
            ury_kot['production_silent_print_format'] = None
            ury_kot['production_silent_print_type'] = None
    
    kitchen_controller_roles = list(set(kitchen_controller_roles))
    
    return {'ury_kots': ury_kots, 'kitchen_controller_roles': kitchen_controller_roles}


@frappe.whitelist()
def getPosProfile():
    branchName = getBranch()
    waiter = frappe.session.user
    bill_present = False
    qz_host = None
    cashier_printer_name = None
    cashier_silent_print_format = None
    cashier_silent_print_type = None
    printer = None
    posProfile = frappe.db.exists("POS Profile", {"branch": branchName})
    pos_profiles = frappe.get_doc("POS Profile", posProfile)

    if pos_profiles.branch == branchName:
        pos_profile_name = pos_profiles.name
        warehouse = pos_profiles.warehouse
        branch = pos_profiles.branch
        company = pos_profiles.company
        tableAttention = pos_profiles.table_attention_time
        get_cashier = frappe.get_doc("POS Profile", pos_profile_name)
        print_format = pos_profiles.print_format
        paid_limit=pos_profiles.paid_limit
        cashier = get_cashier.applicable_for_users[0].user
        qz_print = pos_profiles.qz_print
        silent_print = pos_profiles.custom_silent_print
        enable_kitchen_controller_print = pos_profiles.custom_enable__kitchen_controller_print
        controllers_silent_printers = []
        print_type = None

        for pos_profile in pos_profiles.printer_settings:
            if pos_profile.bill == 1:
                printer = pos_profile.printer
                bill_present = True
                break
        
        if enable_kitchen_controller_print == 1:
            controllers_silent_printers = pos_profiles.custom_kitchen_unit_controllers_silent_print
        
        if silent_print == 1:
            print_type = "silent"

            cashier_silent_print_data = get_cashier_silent_print_format_from_pos_profile(pos_profile_name)
            if cashier_silent_print_data['custom_silent_print_format']:
                cashier_silent_print_format = cashier_silent_print_data['custom_silent_print_format']
                # cashier_silent_print_type = frappe.db.get_value("Silent Print Format", cashier_silent_print_format, "default_print_type")
                cashier_silent_print_type = cashier_silent_print_data['custom_silent_print_type']

        elif qz_print == 1:
            print_type = "qz"

            cashier_qz_data = get_cashier_printer_name_from_pos_profile(pos_profile_name)
            if cashier_qz_data['custom_cashier_printer_name']:
                cashier_printer_name = cashier_qz_data['custom_cashier_printer_name']
            if cashier_qz_data['custom_cashier_qz_host']:
                qz_host = cashier_qz_data['custom_cashier_qz_host']
            else:
                qz_host = pos_profiles.qz_host

        elif bill_present == True:
            print_type = "network"

        else:
            print_type = "socket"

    invoice_details = {
        "pos_profile": pos_profile_name,
        "branch": branch,
        "company": company,
        "waiter": waiter,
        "warehouse": warehouse,
        "cashier": cashier,
        "print_format": print_format,
        "qz_print": qz_print,
        "qz_host": qz_host,
        "cashier_printer_name": cashier_printer_name,
        "enable_kitchen_controller_print": enable_kitchen_controller_print,
        "controllers_silent_printers": controllers_silent_printers,
        "silent_print": silent_print,
        "cashier_silent_print_format": cashier_silent_print_format,
        "cashier_silent_print_type": cashier_silent_print_type,
        "printer": printer,
        "print_type": print_type,
        "tableAttention": tableAttention,
        "paid_limit":paid_limit
    }
    return invoice_details


@frappe.whitelist()
def getPosInvoiceItems(invoice):
    itemDetails = []
    taxDetails = []
    orderdItems = frappe.get_doc("POS Invoice", invoice)
    posItems = orderdItems.items
    for items in posItems:
        item_name = items.item_name
        qty = items.qty
        amount = items.rate
        itemDetails.append(
            {
                "item_name": item_name,
                "qty": qty,
                "amount": amount,
            }
        )
    taxDetail = orderdItems.taxes
    for tax in taxDetail:
        description = tax.description
        rate = tax.tax_amount
        taxDetails.append(
            {
                "description": description,
                "rate": rate,
            }
        )
    return itemDetails, taxDetails


@frappe.whitelist()
def posOpening():
    branchName = getBranch()
    pos_opening_list = frappe.get_all(
        "POS Opening Entry",
        fields=["name", "docstatus", "status", "posting_date"],
        filters={"branch": branchName},
    )
    flag = 1
    for pos_opening in pos_opening_list:
        if pos_opening.status == "Open" and pos_opening.docstatus == 1:
            flag = 0
    if flag == 1:
        frappe.msgprint(title="Message", indicator="red", msg=("Please Open POS Entry"))
    return flag


@frappe.whitelist()
def getAggregator():
    branchName = getBranch()
    aggregatorList = frappe.get_all(
        "Aggregator Settings",
        fields=["customer"],
        filters={"parent": branchName, "parenttype": "Branch"},
    )
    return aggregatorList


@frappe.whitelist()
def getAggregatorItem(aggregator):
    branchName = getBranch()
    aggregatorItem = []
    aggregatorItemList = []
    priceList = frappe.db.get_value(
        "Aggregator Settings",
        {"customer": aggregator, "parent": branchName, "parenttype": "Branch"},
        "price_list",
    )
    aggregatorItem = frappe.get_all(
        "Item Price",
        fields=["item_code", "item_name", "price_list_rate"],
        filters={"selling": 1, "price_list": priceList},
    )
    aggregatorItemList = [
        {
            "item": item.item_code,
            "item_name": item.item_name,
            "rate": item.price_list_rate,
            "item_imgae": frappe.db.get_value("Item", item.item, "image"),
        }
        for item in aggregatorItem
    ]
    return aggregatorItemList

@frappe.whitelist()
def getAggregatorMOP(aggregator):
    branchName = getBranch()
    
    modeOfPayment = frappe.db.get_value(
        "Aggregator Settings",
        {"customer": aggregator, "parent": branchName, "parenttype": "Branch"},
        "mode_of_payments",
    )
    modeOfPaymentsList = []
    modeOfPaymentsList.append(
            {"mode_of_payment": modeOfPayment, "opening_amount": float(0)}
    )
    return modeOfPaymentsList


@frappe.whitelist()
def validate_pos_close(pos_profile): 
    enable_unclosed_pos_check = frappe.db.get_value("POS Profile",pos_profile,"custom_daily_pos_close")
    
    if enable_unclosed_pos_check:
        current_datetime = frappe.utils.now_datetime()
        start_of_day = current_datetime.replace(hour=5, minute=0, second=0, microsecond=0)
        
        if current_datetime > start_of_day:
            previous_day = start_of_day - timedelta(days=1)
            
        else:
            previous_day = start_of_day
    
        unclosed_pos_opening = frappe.db.exists(
            "POS Opening Entry",
            {
                "posting_date": previous_day.date(),
                "status": "Open",
                "pos_profile": pos_profile
            }
        )
    
        if unclosed_pos_opening:
            return "Failed"
        
        return "Success"
    
    return "Success"

