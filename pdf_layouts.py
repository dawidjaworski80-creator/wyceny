from copy import deepcopy
from datetime import datetime


PAGE_WIDTH = 210
PAGE_HEIGHT = 297

FIELD_CATALOG = {
    "quote": (
        ("document_title", "Quote number and title"),
        ("company_block", "Company details"),
        ("customer_block", "Customer details"),
        ("required_date", "Required date"),
        ("customer_po", "Customer PO number"),
        ("items_table", "Quoted items and prices"),
        ("totals_block", "Quote totals"),
        ("company_registration", "Company and VAT registration numbers"),
        ("company_logo", "Company logo"),
        ("custom_text", "Custom text"),
    ),
    "delivery_note": (
        ("document_title", "Delivery note title"),
        ("company_block", "Company details"),
        ("customer_block", "Customer details"),
        ("delivery_meta", "Delivery and order details"),
        ("items_table", "Delivery items"),
        ("signature_block", "Signature fields"),
        ("company_registration", "Company and VAT registration numbers"),
        ("company_logo", "Company logo"),
        ("custom_text", "Custom text"),
    ),
    "job_card": (
        ("document_title", "Job card title"),
        ("company_block", "Company details"),
        ("job_customer", "Customer and job details"),
        ("job_item", "Item, drawing and material details"),
        ("job_operations", "Job operations"),
        ("job_material", "Raw material details"),
        ("company_logo", "Company logo"),
        ("custom_text", "Custom text"),
    ),
}

TABLE_COLUMN_CATALOG = {
    "quote": (
        ("item_no", "Line number"),
        ("name", "Item name"),
        ("drawing_number", "Drawing number"),
        ("revision", "Revision"),
        ("quantity", "Quantity"),
        ("required_date", "Required date"),
        ("material", "Material"),
        ("supplier", "Supplier"),
        ("material_unit_cost", "Material / unit"),
        ("unit_price", "Unit price ex VAT"),
        ("line_total", "Line total ex VAT"),
    ),
    "delivery_note": (
        ("item_no", "Line number"),
        ("name", "Description"),
        ("drawing_number", "Drawing number"),
        ("revision", "Revision"),
        ("quantity", "Quantity"),
        ("required_date", "Required date"),
        ("material", "Material"),
        ("supplier", "Supplier"),
    ),
}

DEFAULT_TABLE_COLUMNS = {
    "quote": (
        "item_no",
        "name",
        "drawing_number",
        "revision",
        "quantity",
        "unit_price",
        "line_total",
    ),
    "delivery_note": (
        "item_no",
        "name",
        "drawing_number",
        "revision",
        "quantity",
    ),
}

TABLE_COLUMN_WIDTH_WEIGHTS = {
    "item_no": 0.45,
    "name": 2.1,
    "drawing_number": 1.4,
    "revision": 0.6,
    "quantity": 0.65,
    "required_date": 1.2,
    "material": 1.4,
    "supplier": 1.3,
    "material_unit_cost": 1.0,
    "unit_price": 1.0,
    "line_total": 1.1,
}


DEFAULT_LAYOUTS = {
    "quote": [
        {"id": "quote-title", "field": "document_title", "label": "", "x": 58, "y": 62, "w": 94, "h": 16, "font_size": 16, "font": "Arial", "style": "B", "color": "#111827", "visible": True},
        {"id": "company", "field": "company_block", "label": "", "x": 119, "y": 10, "w": 80, "h": 43, "font_size": 9, "font": "Arial", "style": "", "color": "#1F2937", "visible": True},
        {"id": "customer", "field": "customer_block", "label": "To:", "x": 12, "y": 38, "w": 95, "h": 38, "font_size": 10, "font": "Arial", "style": "", "color": "#1F2937", "visible": True},
        {"id": "required-date", "field": "required_date", "label": "", "x": 45, "y": 83, "w": 120, "h": 8, "font_size": 10, "font": "Arial", "style": "B", "color": "#1F2937", "visible": True},
        {"id": "items", "field": "items_table", "label": "Items", "x": 12, "y": 99, "w": 186, "h": 110, "font_size": 8, "font": "Arial", "style": "", "color": "#111827", "visible": True},
        {"id": "totals", "field": "totals_block", "label": "", "x": 112, "y": 220, "w": 86, "h": 35, "font_size": 10, "font": "Arial", "style": "", "color": "#111827", "visible": True},
        {"id": "registration", "field": "company_registration", "label": "", "x": 12, "y": 273, "w": 120, "h": 15, "font_size": 8, "font": "Arial", "style": "", "color": "#4B5563", "visible": True, "repeat": True},
        {"id": "logo", "field": "company_logo", "label": "", "x": 12, "y": 10, "w": 38, "h": 22, "font_size": 10, "font": "Arial", "style": "", "color": "#1F2937", "visible": True},
    ],
    "delivery_note": [
        {"id": "delivery-title", "field": "document_title", "label": "", "x": 35, "y": 51, "w": 140, "h": 14, "font_size": 16, "font": "Arial", "style": "B", "color": "#111827", "visible": True},
        {"id": "company", "field": "company_block", "label": "", "x": 102, "y": 10, "w": 96, "h": 36, "font_size": 9, "font": "Arial", "style": "", "color": "#1F2937", "visible": True},
        {"id": "customer", "field": "customer_block", "label": "Deliver to:", "x": 12, "y": 13, "w": 82, "h": 40, "font_size": 10, "font": "Arial", "style": "", "color": "#1F2937", "visible": True},
        {"id": "delivery-meta", "field": "delivery_meta", "label": "Delivery details", "x": 105, "y": 68, "w": 93, "h": 43, "font_size": 9, "font": "Arial", "style": "", "color": "#1F2937", "visible": True},
        {"id": "items", "field": "items_table", "label": "Items / goods", "x": 12, "y": 120, "w": 186, "h": 80, "font_size": 9, "font": "Arial", "style": "", "color": "#111827", "visible": True},
        {"id": "signatures", "field": "signature_block", "label": "", "x": 12, "y": 224, "w": 186, "h": 43, "font_size": 8, "font": "Arial", "style": "", "color": "#1F2937", "visible": True},
        {"id": "registration", "field": "company_registration", "label": "", "x": 12, "y": 273, "w": 120, "h": 15, "font_size": 8, "font": "Arial", "style": "", "color": "#4B5563", "visible": True, "repeat": True},
        {"id": "logo", "field": "company_logo", "label": "", "x": 12, "y": 70, "w": 35, "h": 20, "font_size": 10, "font": "Arial", "style": "", "color": "#1F2937", "visible": True},
    ],
    "job_card": [
        {"id": "job-title", "field": "document_title", "label": "", "x": 48, "y": 9, "w": 114, "h": 13, "font_size": 18, "font": "Arial", "style": "B", "color": "#111827", "visible": True},
        {"id": "company", "field": "company_block", "label": "", "x": 12, "y": 27, "w": 186, "h": 22, "font_size": 8, "font": "Arial", "style": "", "color": "#1F2937", "visible": True},
        {"id": "job-customer", "field": "job_customer", "label": "Customer and Job Information", "x": 12, "y": 53, "w": 186, "h": 38, "font_size": 9, "font": "Arial", "style": "", "color": "#111827", "visible": True},
        {"id": "job-item", "field": "job_item", "label": "Item details", "x": 12, "y": 96, "w": 186, "h": 36, "font_size": 9, "font": "Arial", "style": "", "color": "#111827", "visible": True},
        {"id": "operations", "field": "job_operations", "label": "Operations", "x": 12, "y": 137, "w": 186, "h": 73, "font_size": 9, "font": "Arial", "style": "", "color": "#111827", "visible": True},
        {"id": "raw-material", "field": "job_material", "label": "Raw Material", "x": 12, "y": 215, "w": 186, "h": 38, "font_size": 9, "font": "Arial", "style": "", "color": "#111827", "visible": True},
        {"id": "logo", "field": "company_logo", "label": "", "x": 172, "y": 7, "w": 26, "h": 16, "font_size": 10, "font": "Arial", "style": "", "color": "#1F2937", "visible": True},
    ],
}


def get_layouts(settings):
    saved = settings.get("PDF_Layouts")
    layouts = deepcopy(DEFAULT_LAYOUTS)
    if not isinstance(saved, dict):
        return layouts
    for document_type, elements in saved.items():
        if document_type not in layouts or not isinstance(elements, list):
            continue
        valid_elements = []
        for element in elements:
            if not isinstance(element, dict) or element.get("field") not in {
                field for field, _ in FIELD_CATALOG[document_type]
            }:
                continue
            normalized = deepcopy(element)
            for key, default in (
                ("id", str(normalized.get("field", "field"))),
                ("label", ""),
                ("x", 12),
                ("y", 12),
                ("w", 60),
                ("h", 12),
                ("font_size", 10),
                ("font", "Arial"),
                ("style", ""),
                ("color", "#111827"),
                ("visible", True),
            ):
                normalized.setdefault(key, default)
            if normalized["field"] == "items_table":
                allowed_columns = {
                    field for field, _ in TABLE_COLUMN_CATALOG[document_type]
                }
                selected_columns = normalized.get("table_columns")
                if not isinstance(selected_columns, list):
                    selected_columns = []
                normalized["table_columns"] = [
                    field for field in selected_columns if field in allowed_columns
                ] or list(DEFAULT_TABLE_COLUMNS[document_type])
            valid_elements.append(normalized)
        layouts[document_type] = valid_elements
    return layouts


def _customer_details(data):
    customer = data.get("customer", {})
    if not isinstance(customer, dict):
        customer = {"name": str(customer)}
    lines = [str(customer.get("name", ""))]
    for key in ("address", "contact", "phone", "email"):
        value = str(customer.get(key, "")).strip()
        if value:
            lines.append(value if key == "address" else f"{key.title()}: {value}")
    return "\n".join(line for line in lines if line)


def _company_details(settings):
    keys = (
        ("Company_Name", ""),
        ("Company_Address", ""),
        ("Company_Postcode", ""),
        ("Company_Phone_Landline", "Phone: "),
        ("Company_Phone_Mobile", "Mobile: "),
    )
    lines = []
    for key, prefix in keys:
        value = str(settings.get(key, "")).strip()
        if value:
            lines.append(f"{prefix}{value}")
    return "\n".join(lines)


def _table_cell_text(value, pdf, width):
    text = str(value or "").replace("\n", " ").strip()
    available_width = max(0, width - 2)
    if pdf.get_string_width(text) <= available_width:
        return text
    ellipsis = "..."
    while text and pdf.get_string_width(text + ellipsis) > available_width:
        text = text[:-1]
    return text + ellipsis if text else ""


def _item_table_rows(document_type, data):
    items = [dict(item) for item in data.get("items", [])]
    if not items and "operations" in data:
        items = [
            {
                "name": data.get("name", "Main Part"),
                "drawing_number": data.get("drawing_number", ""),
                "revision": data.get("revision", ""),
                "quantity": 1,
                "req_date": data.get("required_date", ""),
                "material": data.get("material", ""),
                "supplier": data.get("supplier", ""),
                "material_cost": data.get("material_cost", 0),
                "operations": data["operations"],
            }
        ]
    markup = float(data.get("markup", 0.0) or 0.0)
    rows = []
    for line_number, item in enumerate(items, start=1):
        quantity = int(item.get("quantity", 1) or 1)
        material_cost = float(item.get("material_cost", 0) or 0)
        unit_cost = material_cost + sum(
            float(operation.get("cost", 0) or 0)
            for operation in item.get("operations", [])
        )
        unit_price = unit_cost * (1 + markup / 100)
        required_date = str(item.get("req_date", "")).strip()
        if required_date:
            try:
                required_date = datetime.strptime(
                    required_date, "%Y-%m-%d"
                ).strftime("%d.%m.%Y")
            except ValueError:
                pass
        row = {
            "item_no": line_number,
            "name": item.get("name", ""),
            "drawing_number": item.get(
                "drawing_number", data.get("drawing_number", "")
            ),
            "revision": item.get("revision", data.get("revision", "")),
            "quantity": quantity,
            "required_date": required_date,
            "material": item.get("material", ""),
            "supplier": item.get("supplier", ""),
            "material_unit_cost": f"{material_cost:.2f}",
            "unit_price": f"{unit_price:.2f}",
            "line_total": f"{unit_price * quantity:.2f}",
        }
        if document_type == "delivery_note":
            row["quantity"] = item.get("quantity", 1) or 1
        rows.append(row)
    return rows


def _render_items_table(pdf, document_type, data, element, label):
    available_columns = dict(TABLE_COLUMN_CATALOG[document_type])
    columns = [
        column
        for column in element.get("table_columns", DEFAULT_TABLE_COLUMNS[document_type])
        if column in available_columns
    ]
    if not columns:
        columns = list(DEFAULT_TABLE_COLUMNS[document_type])

    x = max(0, min(PAGE_WIDTH - 1, float(element.get("x", 0))))
    width = max(1, min(PAGE_WIDTH - x, float(element.get("w", 60))))
    y = max(0, min(PAGE_HEIGHT - 2, float(element.get("y", 0))))
    font_size = max(5, min(36, int(element.get("font_size", 10))))
    row_height = max(6, font_size * 0.8)
    total_weight = sum(TABLE_COLUMN_WIDTH_WEIGHTS[column] for column in columns)
    column_widths = [
        width * TABLE_COLUMN_WIDTH_WEIGHTS[column] / total_weight
        for column in columns
    ]
    rows = _item_table_rows(document_type, data)

    pdf.set_text_color(17, 24, 39)
    pdf.set_font(str(element.get("font", "Arial")), "B", max(5, font_size))
    if label:
        pdf.set_xy(x, y)
        pdf.multi_cell(width, max(3, font_size * 0.42), str(label))
        y = pdf.get_y() + 1

    def draw_header(header_y):
        pdf.set_xy(x, header_y)
        pdf.set_fill_color(226, 232, 240)
        for column, cell_width in zip(columns, column_widths):
            pdf.cell(
                cell_width,
                row_height,
                _table_cell_text(available_columns[column], pdf, cell_width),
                border=1,
                align="C",
                fill=True,
            )
        return header_y + row_height

    if y + row_height > PAGE_HEIGHT - 12:
        pdf.add_page()
        y = 12
    y = draw_header(y)
    pdf.set_font(str(element.get("font", "Arial")), str(element.get("style", "")), font_size)
    for row in rows:
        if y + row_height > PAGE_HEIGHT - 12:
            pdf.add_page()
            y = draw_header(12)
            pdf.set_font(
                str(element.get("font", "Arial")),
                str(element.get("style", "")),
                font_size,
            )
        pdf.set_xy(x, y)
        for column, cell_width in zip(columns, column_widths):
            value = _table_cell_text(row.get(column, ""), pdf, cell_width)
            align = "R" if column in {
                "item_no",
                "quantity",
                "material_unit_cost",
                "unit_price",
                "line_total",
            } else "L"
            pdf.cell(cell_width, row_height, value, border=1, align=align)
        y += row_height


def _field_values(document_type, data, settings):
    customer = data.get("customer", {})
    if not isinstance(customer, dict):
        customer = {"name": str(customer)}
    required_date = str(data.get("required_date", "")).strip()
    if required_date:
        try:
            required_date = datetime.strptime(required_date, "%Y-%m-%d").strftime("%d.%m.%Y")
        except ValueError:
            pass
    registration = []
    if settings.get("Company_Reg_No"):
        registration.append(f"Company Reg. No.: {settings['Company_Reg_No']}")
    if settings.get("VAT_Reg_No"):
        registration.append(f"VAT Reg. No.: {settings['VAT_Reg_No']}")
    values = {
        "company_block": _company_details(settings),
        "customer_block": _customer_details(data),
        "required_date": f"Date required: {required_date}" if required_date else "",
        "customer_po": str(data.get("customer_po_number", "")),
        "company_registration": "\n".join(registration),
        "company_logo": "",
        "custom_text": "",
    }
    if document_type == "job_card":
        values["company_registration"] = ""
    if document_type == "quote":
        total = 0.0
        markup = float(data.get("markup", 0.0) or 0.0)
        quote_items = [dict(item) for item in data.get("items", [])]
        if not quote_items and "operations" in data:
            quote_items = [{"operations": data["operations"]}]
        for item in quote_items:
            quantity = int(item.get("quantity", 1) or 1)
            unit_cost = float(item.get("material_cost", 0) or 0) + sum(
                float(operation.get("cost", 0) or 0)
                for operation in item.get("operations", [])
            )
            total += unit_cost * quantity * (1 + markup / 100)
        discount = float(data.get("discount", 0.0) or 0.0)
        net_total = total * (1 - discount / 100)
        vat_rate = float(settings.get("VAT_Rate", 20.0) or 0.0)
        vat_total = net_total * vat_rate / 100
        values.update({
            "document_title": (
                f"{'ORDER' if data.get('status') == 'order' else 'QUOTE'} "
                f"NO: {data.get('number', '')}\n{data.get('name', '')}"
            ),
            "items_table": "",
            "totals_block": (
                f"Total (ex VAT): {net_total:.2f}\n"
                f"VAT ({vat_rate:g}%): {vat_total:.2f}\n"
                f"Total (inc VAT): {net_total + vat_total:.2f}"
            ),
        })
    elif document_type == "delivery_note":
        values.update({
            "document_title": "CUSTOMER DELIVERY NOTE",
            "delivery_meta": (
                f"Delivery note no.: {data.get('delivery_note_number', '')}\n"
                f"Date: {datetime.now().strftime('%d.%m.%Y')}\n"
                f"Customer PO number: {data.get('customer_po_number', '')}\n"
                f"Our Order number: {data.get('number', '')}\n"
                f"Date required: {required_date}"
            ),
            "items_table": "",
            "signature_block": (
                "Prepared by / Sender                 Carrier                 Received by\n\n\n"
                "Signature                                      Signature                  Signature\n"
                "Date                                             Date                          Date"
            ),
        })
    else:
        items = [dict(item) for item in data.get("items", [])]
        values.update({
            "document_title": "ROUTE CARD",
            "job_customer": (
                f"Customer: {customer.get('name', '')}\n"
                f"Job No: {data.get('number', '')}    Contact Person: {customer.get('contact', '')}\n"
                f"Customer PO: {data.get('customer_po_number', '')}\n"
                f"Delivery Required: {required_date}"
            ),
            "job_item": "",
            "job_operations": "",
            "job_material": "",
        })
        if items:
            item = items[0]
            values["job_item"] = (
                f"Item: {item.get('name', '')}    Qty: {item.get('quantity', 1) or 1}\n"
                f"Drawing Number: {item.get('drawing_number', '')}    Revision: {item.get('revision', '')}\n"
                f"Material: {item.get('material', '')}    Cast: {item.get('cast', '')}    "
                f"MCT Number: {item.get('mct_number', '')}"
            )
            operations = item.get("operations", []) or [{}]
            values["job_operations"] = (
                "Date                     Operation                     Start Time     End Time       Initials\n"
                + "\n".join(
                    f"________________   {operation.get('type', '')}   "
                    "____________   __________   ________"
                    for operation in operations
                )
            )
            values["job_material"] = (
                f"Supplier: {item.get('supplier', '')}\n"
                f"Description: {item.get('material', '')}    Qty: {item.get('quantity', 1) or 1}"
            )
    return values


def render_layout_pdf(pdf, document_type, data, settings):
    layouts = get_layouts(settings)
    elements = layouts[document_type]
    values = _field_values(document_type, data, settings)
    repeat_elements = []
    for element in elements:
        if not element.get("visible", True):
            continue
        if element.get("repeat"):
            repeat_elements.append(element)
            continue
        field = element.get("field", "")
        if field == "company_logo":
            logo_path = settings.get("Logo_Path", "").strip()
            if logo_path and element.get("w", 0) > 0 and element.get("h", 0) > 0:
                try:
                    pdf.image(
                        logo_path,
                        x=float(element.get("x", 0)),
                        y=float(element.get("y", 0)),
                        w=float(element.get("w", 0)),
                        h=float(element.get("h", 0)),
                    )
                except Exception as exc:
                    raise RuntimeError(f"Could not add the company logo to the PDF: {exc}") from exc
            continue

        if field == "items_table":
            _render_items_table(
                pdf,
                document_type,
                data,
                element,
                element.get("label", ""),
            )
            continue

        text = values.get(field, "")
        if field == "custom_text":
            text = element.get("label", "")
        elif element.get("label"):
            text = f"{element['label']}\n{text}" if text else element["label"]
        if not text:
            continue
        color = str(element.get("color", "#111827")).lstrip("#")
        if len(color) != 6:
            color = "111827"
        try:
            red, green, blue = (int(color[index:index + 2], 16) for index in (0, 2, 4))
            font_size = max(5, min(36, int(element.get("font_size", 10))))
            width = max(1, min(PAGE_WIDTH, float(element.get("w", 60))))
            x = max(0, min(PAGE_WIDTH - width, float(element.get("x", 0))))
            y = max(0, min(PAGE_HEIGHT - 2, float(element.get("y", 0))))
        except (TypeError, ValueError):
            continue
        pdf.set_text_color(red, green, blue)
        pdf.set_font(str(element.get("font", "Arial")), str(element.get("style", "")), font_size)
        pdf.set_xy(x, y)
        pdf.multi_cell(width, max(3, font_size * 0.42), str(text))
    final_page = pdf.page
    for element in repeat_elements:
        field = element.get("field", "")
        text = values.get(field, "")
        if element.get("label"):
            text = f"{element['label']}\n{text}" if text else element["label"]
        if not text:
            continue
        color = str(element.get("color", "#111827")).lstrip("#")
        if len(color) != 6:
            color = "111827"
        try:
            red, green, blue = (int(color[index:index + 2], 16) for index in (0, 2, 4))
            font_size = max(5, min(36, int(element.get("font_size", 10))))
            width = max(1, min(PAGE_WIDTH, float(element.get("w", 60))))
            x = max(0, min(PAGE_WIDTH - width, float(element.get("x", 0))))
            y = max(0, min(PAGE_HEIGHT - 2, float(element.get("y", 0))))
        except (TypeError, ValueError):
            continue
        for page_number in range(1, final_page + 1):
            pdf.page = page_number
            pdf.set_text_color(red, green, blue)
            pdf.set_font(str(element.get("font", "Arial")), str(element.get("style", "")), font_size)
            pdf.set_xy(x, y)
            pdf.multi_cell(width, max(3, font_size * 0.42), str(text))
    pdf.page = final_page
    pdf.set_text_color(0, 0, 0)


def generate_layout_document(document_type, data, settings):
    import os

    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise RuntimeError("FPDF library not installed. Please install fpdf2.") from exc

    if document_type not in FIELD_CATALOG:
        raise RuntimeError(f"Unknown PDF document type: {document_type}")
    if document_type in ("delivery_note", "job_card") and data.get("status") != "order":
        label = "delivery note" if document_type == "delivery_note" else "job card"
        raise RuntimeError(f"A {label} can only be generated for an order.")
    logo_path = str(settings.get("Logo_Path", "")).strip()
    if logo_path:
        if not os.path.isfile(logo_path):
            raise RuntimeError(f"Company logo file not found: {logo_path}")
        if os.path.splitext(logo_path)[1].lower() not in (".png", ".jpg", ".jpeg"):
            raise RuntimeError("Company logo must be a PNG or JPEG image.")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    data_for_rendering = deepcopy(data)
    if document_type == "job_card":
        items = data_for_rendering.get("items", [])
        if not items and "operations" in data_for_rendering:
            items = [
                {
                    "name": data_for_rendering.get("name", "Main Part"),
                    "operations": data_for_rendering["operations"],
                }
            ]
        if not items:
            raise RuntimeError("This order has no items to include on a job card.")
        page_items = items
    else:
        page_items = [None]

    for item in page_items:
        pdf.add_page()
        page_data = deepcopy(data_for_rendering)
        if item is not None:
            page_data["items"] = [item]
        render_layout_pdf(pdf, document_type, page_data, settings)

    number = str(
        data.get("delivery_note_number", data.get("number", "Document"))
        if document_type == "delivery_note"
        else data.get("number", "Document")
    ).strip() or "Document"
    safe_number = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in number
    )
    prefix = {
        "quote": "Quote",
        "delivery_note": "Delivery_Note",
        "job_card": "Job_Card",
    }[document_type]
    filename = f"{prefix}_{safe_number}.pdf"
    output_directory = str(settings.get("Pdf_Output_Directory", "")).strip()
    if output_directory:
        if not os.path.isdir(output_directory):
            raise RuntimeError(f"PDF save folder does not exist: {output_directory}")
        filename = os.path.join(output_directory, filename)
    try:
        pdf.output(filename)
    except OSError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Could not save the generated PDF: {exc}") from exc
    return os.path.abspath(filename)
