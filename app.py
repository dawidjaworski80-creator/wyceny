import calendar
from copy import deepcopy
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser, simpledialog
from datetime import date, datetime, timedelta
import math
import os
import re
import tempfile

from data_store import DataStore
from email_service import EmailService
from pdf_service import PdfService
from pdf_layouts import (
    DEFAULT_LAYOUTS,
    DEFAULT_TABLE_COLUMNS,
    FIELD_CATALOG,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    TABLE_COLUMN_CATALOG,
    generate_layout_document,
    get_layouts,
)


def _parse_software_end_datetime(value):
    value = str(value).strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError:
        return datetime.strptime(value, "%Y-%m-%d").replace(
            hour=23,
            minute=59,
        )


class GridTreeview(ttk.Treeview):
    def __init__(self, *args, **kwargs):
        data_columns = tuple(kwargs.get("columns", ()))
        self.separator_columns = tuple(
            f"__grid_separator_{index}" for index in range(len(data_columns) - 1)
        )
        kwargs["columns"] = data_columns + self.separator_columns
        super().__init__(*args, **kwargs)
        self.tag_configure("grid_even", background="#FFFFFF")
        self.tag_configure("grid_odd", background="#EEF2F7")
        displayed_columns = []
        for index, column in enumerate(data_columns):
            displayed_columns.append(column)
            if index < len(self.separator_columns):
                separator = self.separator_columns[index]
                displayed_columns.append(separator)
                self.heading(separator, text="")
                self.column(
                    separator,
                    width=8,
                    minwidth=8,
                    stretch=False,
                    anchor=tk.CENTER,
                )
        self.configure(displaycolumns=displayed_columns)

    def insert(self, parent, index, iid=None, **kwargs):
        row_number = len(self.get_children(parent))
        row_tag = "grid_even" if row_number % 2 == 0 else "grid_odd"
        existing_tags = kwargs.get("tags", ())
        if isinstance(existing_tags, str):
            existing_tags = (existing_tags,)
        kwargs["tags"] = (row_tag, *existing_tags)
        values = tuple(kwargs.get("values", ()))
        kwargs["values"] = values + ("│",) * len(self.separator_columns)
        return super().insert(parent, index, iid=iid, **kwargs)


class CncQuotesApp:
    def __init__(self, root):
        self.root = root
        self.root.title(" - Quoting System")
        self.root.geometry("1100x550")
        self.root.state("zoomed")
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(
            "Treeview",
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
            borderwidth=1,
            relief="solid",
            rowheight=26,
        )
        style.configure(
            "Treeview.Heading",
            background="#E2E8F0",
            bordercolor="#64748B",
            borderwidth=1,
            relief="solid",
        )

        self.store = DataStore()
        self.settings = self.store.load_settings()
        self.customers = self.store.load_customers()
        if self._normalize_customers() and not self.software_is_expired():
            self.save_customers()
        self.suppliers = self.store.load_suppliers()
        self.quotes = self.store.load_data()
        self.quote_clipboard = None
        self.item_clipboard = None
        suppliers_updated = False
        for quote in self.quotes:
            for item in quote.get("items", []):
                supplier_name = str(item.get("supplier", "")).strip()
                if supplier_name and supplier_name not in self.suppliers:
                    self.suppliers[supplier_name] = {"address": "", "contact": ""}
                    suppliers_updated = True
        if suppliers_updated and not self.software_is_expired():
            self.store.save_suppliers(self.suppliers)
        self.current_view = "home"

        self.create_widgets()
        self.refresh_list()

    def save_data(self):
        self.store.save_data(self.quotes)

    def save_settings(self):
        self.store.save_settings(self.settings)

    def save_customers(self):
        self.store.save_customers(self.customers)

    @staticmethod
    def clear_zero_on_click(entry):
        def clear_zero(event=None):
            value = entry.get().strip().replace(",", ".")
            try:
                is_zero = float(value) == 0
            except ValueError:
                return
            if is_zero:
                entry.delete(0, tk.END)

        entry.bind("<Button-1>", clear_zero)

    @staticmethod
    def bind_enter_to_next(*widgets):
        def focus_next_input(event):
            current = event.widget
            candidate = current.tk_focusNext()
            visited = set()
            while candidate is not current and str(candidate) not in visited:
                visited.add(str(candidate))
                if isinstance(candidate, (tk.Entry, ttk.Combobox, tk.Text)):
                    state = candidate.cget("state")
                    is_combobox = isinstance(candidate, ttk.Combobox)
                    if state != tk.DISABLED and (is_combobox or state != "readonly"):
                        candidate.focus_set()
                        return "break"
                candidate = candidate.tk_focusNext()
            return "break"

        def insert_multiline_newline(event):
            event.widget.insert(tk.INSERT, "\n")
            return "break"

        for widget in widgets:
            widget.bind("<Return>", focus_next_input, add="+")
            if isinstance(widget, tk.Text):
                widget.bind("<Shift-Return>", insert_multiline_newline, add="+")

    @staticmethod
    def capitalize_words_on_focus_out(widget):
        focus_start_value = {"value": None}

        def remember_value(event=None):
            if isinstance(widget, tk.Text):
                focus_start_value["value"] = widget.get("1.0", "end-1c")
            else:
                focus_start_value["value"] = widget.get()

        def capitalize_words(event=None):
            is_text_widget = isinstance(widget, tk.Text)
            if is_text_widget:
                value = widget.get("1.0", "end-1c")
            else:
                value = widget.get()
            if value == focus_start_value["value"]:
                return
            capitalized = re.sub(
                r"(?<!\w)([^\W\d_])",
                lambda match: match.group(1).upper(),
                value,
                flags=re.UNICODE,
            )
            if capitalized == value:
                return
            if is_text_widget:
                widget.delete("1.0", tk.END)
                widget.insert("1.0", capitalized)
            else:
                cursor_position = widget.index(tk.INSERT)
                widget.delete(0, tk.END)
                widget.insert(0, capitalized)
                widget.icursor(min(cursor_position, len(capitalized)))

        widget.bind("<FocusIn>", remember_value, add="+")
        widget.bind("<FocusOut>", capitalize_words, add="+")

    def maximize_window(self, window):
        window.update_idletasks()
        window.state("zoomed")

    def _normalize_customers(self):
        changed = False
        for company, data in list(self.customers.items()):
            if not isinstance(data, dict):
                normalized = {"address": "", "contacts": {}}
                changed = True
                self.customers[company] = normalized
                continue

            contacts = data.get("contacts")
            if not isinstance(contacts, dict):
                contacts = {}
                contact_name = str(data.get("contact", "")).strip()
                if contact_name:
                    contacts[contact_name] = {
                        "phone": data.get("phone", ""),
                        "email": data.get("email", ""),
                    }

            normalized = {
                "address": data.get("address", ""),
                "contacts": contacts,
            }
            if data != normalized:
                changed = True
            self.customers[company] = normalized
        return changed

    def calculate_quote_totals(self, items, discount_pct, markup_pct=0.0):
        cost_subtotal = 0.0
        for item in items:
            quantity = int(item.get("quantity", 1) or 1)
            item_cost = float(item.get("material_cost", 0) or 0)
            for op in item.get("operations", []):
                item_cost += float(op.get("cost", 0))
            cost_subtotal += item_cost * quantity

        subtotal = cost_subtotal * (1 + markup_pct / 100.0)
        discount_amt = subtotal * (discount_pct / 100.0)
        net_total = subtotal - discount_amt
        vat_rate = self.settings.get("VAT_Rate", 20.0)
        vat_amt = net_total * (vat_rate / 100.0)
        gross_total = net_total + vat_amt

        return subtotal, discount_amt, net_total, vat_amt, gross_total

    def open_required_date_calendar(self, parent, initial_date, on_select):
        popup = tk.Toplevel(parent)
        popup.title("Select Required Date")
        popup.transient(parent)
        popup.resizable(False, False)
        popup.grab_set()

        selected_month = {"year": initial_date.year, "month": initial_date.month}
        month_label = tk.Label(popup, font=("Arial", 11, "bold"))
        month_label.grid(row=0, column=1, padx=8, pady=8)
        day_frame = tk.Frame(popup)
        day_frame.grid(row=2, column=0, columnspan=7, padx=8, pady=4)

        def show_month():
            year = selected_month["year"]
            month = selected_month["month"]
            month_label.config(text=f"{calendar.month_name[month]} {year}")
            for child in day_frame.winfo_children():
                child.destroy()

            for column, weekday in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
                tk.Label(day_frame, text=weekday, width=4, font=("Arial", 9, "bold")).grid(
                    row=0, column=column
                )

            for row, week in enumerate(calendar.monthcalendar(year, month), start=1):
                for column, day_number in enumerate(week):
                    if day_number:
                        chosen_date = date(year, month, day_number)
                        tk.Button(
                            day_frame,
                            text=str(day_number),
                            width=3,
                            command=lambda value=chosen_date: select_date(value),
                        ).grid(row=row, column=column, padx=1, pady=1)

        def change_month(amount):
            month_index = selected_month["year"] * 12 + selected_month["month"] - 1 + amount
            selected_month["year"], month_offset = divmod(month_index, 12)
            selected_month["month"] = month_offset + 1
            show_month()

        def select_date(chosen_date):
            on_select(chosen_date)
            popup.destroy()

        tk.Button(popup, text="<", width=3, command=lambda: change_month(-1)).grid(
            row=0, column=0, padx=8, pady=8
        )
        tk.Button(popup, text=">", width=3, command=lambda: change_month(1)).grid(
            row=0, column=2, padx=8, pady=8
        )
        show_month()

    def create_widgets(self):
        navigation = tk.Frame(self.root, bg="#1F2937")
        navigation.pack(side=tk.TOP, fill=tk.X)

        self.logo_label = tk.Label(navigation, bg="#1F2937", fg="white")
        self.logo_label.pack(side=tk.LEFT, padx=(12, 8), pady=4)
        self.refresh_app_logo()

        self.nav_buttons = {}
        nav_items = (
            ("home", "Home", self.show_home, "#64748B"),
            ("quotes", "Quotes", self.show_quotes, "#2563EB"),
            ("new_quote", "New Quote", self.add_quote, "#059669"),
            ("orders", "Orders", self.show_orders, "#7C3AED"),
        )
        for view, label, command, color in nav_items:
            button = tk.Button(
                navigation,
                text=label,
                command=command,
                bg="#334155",
                fg="white",
                activebackground=color,
                activeforeground="white",
                relief=tk.FLAT,
                borderwidth=0,
                highlightthickness=0,
                cursor="hand2",
                padx=16,
                pady=10,
                font=("Arial", 10, "bold"),
            )
            button.pack(side=tk.LEFT, padx=(10 if not self.nav_buttons else 4, 4), pady=8)
            self.nav_buttons[view] = (button, color)

        utility_buttons = (
            ("Customer Database", self.open_customer_database),
            ("Suppliers", self.open_supplier_database),
            ("Settings", self.open_settings_window),
        )
        for label, command in utility_buttons:
            button = tk.Button(
                navigation,
                text=label,
                command=command,
                bg="#334155",
                fg="#E2E8F0",
                activebackground="#475569",
                activeforeground="white",
                relief=tk.FLAT,
                borderwidth=0,
                highlightthickness=0,
                cursor="hand2",
                padx=12,
                pady=10,
                font=("Arial", 9, "bold"),
            )
            button.pack(side=tk.RIGHT, padx=4, pady=8)
            button.bind("<Enter>", lambda event: event.widget.configure(bg="#475569"))
            button.bind("<Leave>", lambda event: event.widget.configure(bg="#334155"))

        self.action_frame = tk.Frame(self.root, bg="#F1F5F9")
        self.action_frame.pack(side=tk.TOP, fill=tk.X)

        self.edit_button = tk.Button(self.action_frame, text="Edit Quote", command=self.edit_quote, width=15)
        self.edit_button.pack(side=tk.LEFT, padx=(10, 5), pady=8)
        self.copy_quote_button = tk.Button(
            self.action_frame,
            text="Copy Quote",
            command=self.copy_selected_quote,
            width=13,
        )
        self.copy_quote_button.pack(side=tk.LEFT, padx=5, pady=8)
        self.paste_quote_button = tk.Button(
            self.action_frame,
            text="Paste Quote",
            command=self.paste_quote,
            width=13,
        )
        self.paste_quote_button.pack(side=tk.LEFT, padx=5, pady=8)
        self.delete_button = tk.Button(self.action_frame, text="Delete Quote", command=self.delete_quote, width=15)
        self.delete_button.pack(side=tk.LEFT, padx=5, pady=8)
        self.convert_button = tk.Button(self.action_frame, text="Change to Order", command=self.convert_to_order, width=17)
        self.convert_button.pack(side=tk.LEFT, padx=5, pady=8)
        self.convert_to_quote_button = tk.Button(
            self.action_frame,
            text="Change to Quote",
            command=self.convert_to_quote,
            width=17,
        )
        self.convert_to_quote_button.pack(side=tk.LEFT, padx=5, pady=8)
        self.search_var = tk.StringVar()
        self.search_frame = tk.Frame(self.action_frame, bg="#F1F5F9")
        tk.Label(
            self.search_frame,
            text="Search name, drawing, order/quote no. or Customer PO:",
            bg="#F1F5F9",
        ).pack(side=tk.LEFT, padx=(8, 4))
        self.search_entry = tk.Entry(self.search_frame, textvariable=self.search_var, width=24)
        self.search_entry.pack(side=tk.LEFT, padx=4)
        self.search_button = tk.Button(
            self.search_frame,
            text="Search",
            command=self.search_records,
        )
        self.search_button.pack(side=tk.LEFT, padx=4)
        self.clear_search_button = tk.Button(
            self.search_frame,
            text="Clear",
            command=self.clear_search,
        )
        self.clear_search_button.pack(side=tk.LEFT, padx=4)
        self.search_entry.bind("<Return>", lambda event: self.search_records())

        self.view_label = tk.Label(self.root, text="Latest Orders", font=("Arial", 16, "bold"))
        self.view_label.pack(anchor=tk.W, padx=15, pady=(12, 4))

        columns = (
            "number",
            "customer",
            "customer_po",
            "name",
            "required_date",
            "gross_total",
            "order_status",
            "job_card",
        )
        self.tree = GridTreeview(self.root, columns=columns, show="tree headings")
        self.tree.heading("#0", text="Line")
        self.tree.column("#0", width=55, anchor=tk.CENTER, stretch=False)
        self.tree.heading("number", text="No.")
        self.tree.heading("customer", text="Customer")
        self.tree.heading("customer_po", text="Customer PO Number")
        self.tree.heading("name", text="Quote Description")
        self.tree.heading("required_date", text="Date Required")
        self.tree.heading("gross_total", text="Gross Total (£/$)")
        self.tree.heading("order_status", text="Status")
        self.tree.heading("job_card", text="Job Card")

        self.tree.column("number", width=50, anchor=tk.CENTER)
        self.tree.column("customer", width=200)
        self.tree.column("customer_po", width=155)
        self.tree.column("name", width=250)
        self.tree.column("required_date", width=145, anchor=tk.CENTER)
        self.tree.column("gross_total", width=120, anchor=tk.E)
        self.tree.column("order_status", width=110, anchor=tk.CENTER)
        self.tree.column("job_card", width=170, anchor=tk.CENTER, stretch=False)

        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.tree.bind("<Button-1>", self.handle_job_card_click, add="+")
        self.tree.bind("<Motion>", self.update_tree_cursor)
        self.tree.bind("<Leave>", lambda event: self.tree.configure(cursor=""))
        self.tree.bind("<Double-1>", self.handle_tree_double_click)

    def refresh_app_logo(self):
        logo_path = self.settings.get("Logo_Path", "").strip()
        self.logo_image = None

        if not logo_path:
            self.logo_label.config(image="", text="")
            return
        if not os.path.isfile(logo_path):
            self.logo_label.config(image="", text="Logo not found")
            return

        try:
            from PIL import Image, ImageTk

            image = Image.open(logo_path)
            image.thumbnail((140, 54), Image.LANCZOS)
            self.logo_image = ImageTk.PhotoImage(image)
        except ImportError:
            try:
                image = tk.PhotoImage(file=logo_path)
                width_ratio = max(1, (image.width() + 139) // 140)
                height_ratio = max(1, (image.height() + 53) // 54)
                divisor = max(width_ratio, height_ratio)
                if divisor > 1:
                    image = image.subsample(divisor, divisor)
                self.logo_image = image
            except tk.TclError:
                self.logo_label.config(
                    image="",
                    text="JPG logo requires Pillow",
                )
                return
        except (OSError, ValueError, tk.TclError) as exc:
            self.logo_label.config(image="", text=f"Logo error: {exc}")
            return

        self.logo_label.config(image=self.logo_image, text="")

    def refresh_list(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        orders = [q for q in self.quotes if q.get("status", "quote") == "order"]
        if self.current_view == "home":
            visible_quotes = sorted(orders, key=lambda q: int(q.get("number", 0)), reverse=True)[:10]
            self.view_label.config(text="Latest Orders")
        elif self.current_view == "orders":
            visible_quotes = orders
            self.view_label.config(text="Orders")
        else:
            visible_quotes = [q for q in self.quotes if q.get("status", "quote") != "order"]
            self.view_label.config(text="Quotes")

        visible_columns = (
            ("number", "customer", "customer_po", "name", "required_date", "gross_total", "order_status", "job_card")
            if self.current_view == "orders"
            else ("number", "customer", "name", "required_date", "gross_total", "order_status", "job_card")
        )
        data_columns = tuple(self.tree["columns"])
        column_indices = {column: index for index, column in enumerate(data_columns)}
        display_columns = []
        for index, column in enumerate(visible_columns):
            display_columns.append(column)
            if index < len(visible_columns) - 1:
                display_columns.append(
                    self.tree.separator_columns[column_indices[column]]
                )
        self.tree.configure(displaycolumns=display_columns)

        search_text = self.search_var.get().strip().casefold()
        if self.current_view in ("orders", "quotes") and search_text:
            def matches_search(record):
                item_values = []
                items = record.get("items", [])
                for item in items:
                    item_values.extend((
                        item.get("name", ""),
                        item.get("drawing_number", ""),
                    ))
                customer = record.get("customer", {})
                customer_name = (
                    customer.get("name", "")
                    if isinstance(customer, dict)
                    else customer
                )
                fields = (
                    record.get("name", ""),
                    customer_name,
                    record.get("number", ""),
                    record.get("customer_po_number", ""),
                    record.get("drawing_number", ""),
                    *item_values,
                )
                return any(search_text in str(value).casefold() for value in fields)

            visible_quotes = [q for q in visible_quotes if matches_search(q)]

        for line_number, q in enumerate(visible_quotes, start=1):
            discount_pct = float(q.get("discount", 0.0))

            items = q.get("items", [])
            if not items and "operations" in q:
                items = [{"operations": q["operations"]}]

            _, _, _, _, gross_total = self.calculate_quote_totals(
                items,
                discount_pct,
                float(q.get("markup", 0.0) or 0.0),
            )

            customer_name = q.get("customer", {}).get("name", q.get("customer", "Unknown")) if isinstance(q.get("customer"), dict) else q.get("customer", "")
            required_date = str(q.get("required_date", "")).strip()
            if required_date:
                for date_format in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"):
                    try:
                        required_date = datetime.strptime(required_date, date_format).strftime("%d.%m.%Y")
                        break
                    except ValueError:
                        continue
                date_option = q.get("required_date_option", "")
                if date_option and date_option != "Specific date":
                    required_date = f"{required_date} ({date_option})"
            job_card_generated = (
                q.get("job_card_generated")
                or q.get("order_status") == "Generated"
            )
            job_card_generated_date = q.get("job_card_generated_date", "")
            job_card_label = (
                f"Generated {job_card_generated_date}".strip()
                if job_card_generated
                else "Generate"
            )
            self.tree.insert(
                "",
                tk.END,
                iid=f"record_{id(q)}",
                text=str(line_number),
                values=(
                    q["number"],
                    customer_name,
                    q.get("customer_po_number", ""),
                    q.get("name", ""),
                    required_date,
                    f"{gross_total:.2f}",
                    (
                        "Pending"
                        if q.get("order_status") == "Generated"
                        else q.get("order_status", "Pending")
                    ) if q.get("status") == "order" else "",
                    job_card_label if q.get("status") == "order" else "",
                ),
            )

        is_orders = self.current_view in ("orders", "home")
        self.edit_button.config(text="Edit Order" if is_orders else "Edit Quote")
        self.delete_button.config(text="Delete Order" if is_orders else "Delete Quote")
        if self.current_view == "quotes":
            self.copy_quote_button.pack(side=tk.LEFT, padx=5, pady=8)
            self.paste_quote_button.pack(side=tk.LEFT, padx=5, pady=8)
            self.convert_button.pack(side=tk.LEFT, padx=5, pady=8)
            self.convert_to_quote_button.pack_forget()
            self.search_frame.pack(side=tk.RIGHT, padx=8, pady=4)
            if not self.action_frame.winfo_manager():
                self.action_frame.pack(side=tk.TOP, fill=tk.X, before=self.view_label)
        elif self.current_view == "orders":
            self.copy_quote_button.pack_forget()
            self.paste_quote_button.pack_forget()
            self.convert_button.pack_forget()
            self.convert_to_quote_button.pack(side=tk.LEFT, padx=5, pady=8)
            self.search_frame.pack(side=tk.RIGHT, padx=8, pady=4)
            if not self.action_frame.winfo_manager():
                self.action_frame.pack(side=tk.TOP, fill=tk.X, before=self.view_label)
        else:
            self.search_frame.pack_forget()
            self.action_frame.pack_forget()
        if self.current_view != "quotes":
            self.copy_quote_button.pack_forget()
            self.paste_quote_button.pack_forget()
            self.convert_button.pack_forget()
        if self.current_view != "orders":
            self.convert_to_quote_button.pack_forget()
        for view, (button, color) in self.nav_buttons.items():
            is_current_view = view == self.current_view
            button.config(
                bg=color if is_current_view else "#334155",
                activebackground=color,
                relief=tk.FLAT,
            )

    def handle_job_card_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return

        action_column = len(self.tree["displaycolumns"])
        if self.tree.identify_column(event.x) != f"#{action_column}":
            return

        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return "break"

        job_card_value = self.tree.set(row_id, "job_card")
        if job_card_value != "Generate" and not job_card_value.startswith("Generated"):
            return

        order_number = int(self.tree.set(row_id, "number"))
        order = next(
            (
                record
                for record in self.quotes
                if int(record["number"]) == order_number
                and record.get("status") == "order"
            ),
            None,
        )
        if order is not None:
            self.generate_job_card(order=order)
        return "break"

    def update_tree_cursor(self, event):
        action_column = len(self.tree["displaycolumns"])
        row_id = self.tree.identify_row(event.y)
        is_job_card_action = (
            self.tree.identify_region(event.x, event.y) == "cell"
            and self.tree.identify_column(event.x) == f"#{action_column}"
            and bool(row_id)
            and (
                self.tree.set(row_id, "job_card") == "Generate"
                or self.tree.set(row_id, "job_card").startswith("Generated")
            )
        )
        self.tree.configure(cursor="hand2" if is_job_card_action else "")

    def handle_tree_double_click(self, event):
        action_column = len(self.tree["displaycolumns"])
        if (
            self.tree.identify_region(event.x, event.y) == "cell"
            and self.tree.identify_column(event.x) == f"#{action_column}"
        ):
            return "break"
        self.edit_quote()

    def show_home(self):
        self.current_view = "home"
        self.refresh_list()

    def show_quotes(self):
        self.current_view = "quotes"
        self.refresh_list()

    def show_orders(self):
        self.current_view = "orders"
        self.refresh_list()

    def search_records(self):
        self.refresh_list()

    def clear_search(self):
        self.search_var.set("")
        self.refresh_list()

    def open_customer_database(self):
        window = tk.Toplevel(self.root)
        window.title("Customer Database")
        window.geometry("1050x650")
        self.maximize_window(window)
        window.transient(self.root)

        action_bar = tk.Frame(window, bg="#E2E8F0")
        action_bar.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)
        tk.Button(
            action_bar,
            text="+",
            command=lambda: open_customer_form("new"),
            width=3,
            font=("Arial", 14, "bold"),
        ).pack(side=tk.LEFT, padx=5, pady=4)
        tk.Button(
            action_bar,
            text="Add Contact",
            command=lambda: add_contact_to_selected_company(),
        ).pack(side=tk.LEFT, padx=5, pady=4)
        tk.Label(action_bar, text="Double-click a row to edit").pack(side=tk.LEFT, padx=6)

        columns = ("company", "contact", "address", "phone", "email")
        table_frame = tk.Frame(window)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        database_tree = GridTreeview(table_frame, columns=columns, show="tree headings")
        database_tree.heading("#0", text="Line")
        database_tree.column("#0", width=55, anchor=tk.CENTER, stretch=False)
        for column, label in (
            ("company", "Company"),
            ("contact", "Contact Person"),
            ("address", "Address"),
            ("phone", "Phone"),
            ("email", "Email"),
        ):
            database_tree.heading(column, text=label)
        database_tree.column("company", width=150)
        database_tree.column("contact", width=150)
        database_tree.column("address", width=280)
        database_tree.column("phone", width=140)
        database_tree.column("email", width=220)
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=database_tree.yview)
        database_tree.configure(yscrollcommand=scrollbar.set)
        database_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        status_label = tk.Label(
            window,
            text="Use + to add a company, Add Contact for another person, or double-click a row to edit.",
            anchor=tk.W,
        )
        status_label.pack(fill=tk.X, padx=12, pady=(0, 8))

        def refresh_database(select_company=None, select_contact=None):
            for row in database_tree.get_children():
                database_tree.delete(row)

            line_number = 0
            for company_name in sorted(self.customers, key=str.casefold):
                company = self.customers[company_name]
                contacts = company.get("contacts", {})
                rows = sorted(contacts.items(), key=lambda item: item[0].casefold())
                if not rows:
                    rows = [("", {})]
                for person, details in rows:
                    line_number += 1
                    database_tree.insert(
                        "",
                        tk.END,
                        text=str(line_number),
                        values=(
                            company_name,
                            person,
                            company.get("address", ""),
                            details.get("phone", ""),
                            details.get("email", ""),
                        ),
                    )

            if select_company is not None:
                for row in database_tree.get_children():
                    values = database_tree.item(row, "values")[:len(columns)]
                    if values[0] == select_company and values[1] == (select_contact or ""):
                        database_tree.selection_set(row)
                        database_tree.focus(row)
                        database_tree.see(row)
                        break

        def open_customer_form(mode, row_values=None):
            if self.show_changes_blocked(window):
                return

            row_values = row_values or ("", "", "", "", "")
            company_name, contact_name, address, phone, email = row_values
            old_company_name = company_name if mode in ("edit", "add_contact") else None
            old_contact_name = contact_name if mode == "edit" and contact_name else None
            edit_mode = mode == "edit"
            add_contact_mode = mode == "add_contact"

            dialog = tk.Toplevel(window)
            dialog.title(
                "Edit Customer"
                if edit_mode
                else "Add Contact" if add_contact_mode else "Add Company"
            )
            dialog.geometry("620x340")
            dialog.transient(window)
            dialog.grab_set()
            dialog.columnconfigure(1, weight=1)

            tk.Label(dialog, text="Company:").grid(row=0, column=0, sticky="e", padx=8, pady=7)
            company_entry = ttk.Combobox(dialog, values=sorted(self.customers), width=45)
            company_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=7)
            company_entry.set(company_name)
            if add_contact_mode:
                company_entry.configure(state="readonly")
            self.capitalize_words_on_focus_out(company_entry)

            tk.Label(dialog, text="Contact Person:").grid(row=1, column=0, sticky="e", padx=8, pady=7)
            contact_entry = tk.Entry(dialog)
            contact_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=7)
            contact_entry.insert(0, contact_name)
            self.capitalize_words_on_focus_out(contact_entry)

            tk.Label(dialog, text="Company Address:").grid(row=2, column=0, sticky="ne", padx=8, pady=7)
            address_entry = tk.Text(dialog, height=3, wrap=tk.WORD)
            address_entry.grid(row=2, column=1, sticky="ew", padx=8, pady=7)
            address_entry.insert("1.0", address)
            self.capitalize_words_on_focus_out(address_entry)

            tk.Label(dialog, text="Phone:").grid(row=3, column=0, sticky="e", padx=8, pady=7)
            phone_entry = tk.Entry(dialog)
            phone_entry.grid(row=3, column=1, sticky="ew", padx=8, pady=7)
            phone_entry.insert(0, phone)

            tk.Label(dialog, text="Email:").grid(row=4, column=0, sticky="e", padx=8, pady=7)
            email_entry = tk.Entry(dialog)
            email_entry.grid(row=4, column=1, sticky="ew", padx=8, pady=7)
            email_entry.insert(0, email)

            def save_customer():
                if self.show_changes_blocked(dialog):
                    return

                new_company_name = company_entry.get().strip()
                new_contact_name = contact_entry.get().strip()
                if not new_company_name:
                    messagebox.showwarning("Company required", "Enter a company name.", parent=dialog)
                    return
                if old_contact_name and not new_contact_name:
                    messagebox.showwarning(
                        "Contact required",
                        "A contact name is required when editing a contact.",
                        parent=dialog,
                    )
                    return

                updated_customers = deepcopy(self.customers)
                updated_address = address_entry.get("1.0", tk.END).strip()
                if add_contact_mode and not new_contact_name:
                    messagebox.showwarning(
                        "Contact required",
                        "Enter a contact name.",
                        parent=dialog,
                    )
                    return

                if add_contact_mode:
                    company = updated_customers.get(old_company_name)
                    if company is None:
                        messagebox.showerror(
                            "Company not found",
                            "The selected company no longer exists. Refresh the database and try again.",
                            parent=dialog,
                        )
                        return
                    contacts = company.setdefault("contacts", {})
                    if new_contact_name in contacts:
                        messagebox.showerror(
                            "Contact already exists",
                            f"A contact named {new_contact_name} already exists for this company.",
                            parent=dialog,
                        )
                        return
                    company["address"] = updated_address
                    contacts[new_contact_name] = {
                        "phone": phone_entry.get().strip(),
                        "email": email_entry.get().strip(),
                    }
                elif not edit_mode:
                    if new_company_name in updated_customers:
                        messagebox.showerror(
                            "Company already exists",
                            f"A company named {new_company_name} already exists.",
                            parent=dialog,
                        )
                        return
                    updated_customers[new_company_name] = {
                        "address": updated_address,
                        "contacts": {},
                    }
                    if new_contact_name:
                        updated_customers[new_company_name]["contacts"][new_contact_name] = {
                            "phone": phone_entry.get().strip(),
                            "email": email_entry.get().strip(),
                        }
                elif old_company_name not in updated_customers:
                    messagebox.showerror(
                        "Company not found",
                        "The selected company no longer exists. Refresh the database and try again.",
                        parent=dialog,
                    )
                    return
                elif old_contact_name:
                    old_company = updated_customers[old_company_name]
                    contacts = old_company.setdefault("contacts", {})
                    if old_contact_name not in contacts:
                        messagebox.showerror(
                            "Contact not found",
                            "The selected contact no longer exists. Refresh the database and try again.",
                            parent=dialog,
                        )
                        return
                    if new_company_name != old_company_name and new_company_name not in updated_customers:
                        messagebox.showerror(
                            "Company not found",
                            "Choose an existing company when moving a contact.",
                            parent=dialog,
                        )
                        return
                    contacts.pop(old_contact_name)
                    target_company = updated_customers[new_company_name]
                    target_contacts = target_company.setdefault("contacts", {})
                    if new_contact_name in target_contacts:
                        messagebox.showerror(
                            "Contact already exists",
                            f"A contact named {new_contact_name} already exists for this company.",
                            parent=dialog,
                        )
                        return
                    target_company["address"] = updated_address
                    target_contacts[new_contact_name] = {
                        "phone": phone_entry.get().strip(),
                        "email": email_entry.get().strip(),
                    }
                else:
                    if new_company_name != old_company_name and new_company_name in updated_customers:
                        messagebox.showerror(
                            "Company already exists",
                            f"A company named {new_company_name} already exists.",
                            parent=dialog,
                        )
                        return
                    company = updated_customers.pop(old_company_name)
                    company["address"] = updated_address
                    company.setdefault("contacts", {})
                    if new_contact_name:
                        if new_contact_name in company["contacts"]:
                            messagebox.showerror(
                                "Contact already exists",
                                f"A contact named {new_contact_name} already exists for this company.",
                                parent=dialog,
                            )
                            return
                        company["contacts"][new_contact_name] = {
                            "phone": phone_entry.get().strip(),
                            "email": email_entry.get().strip(),
                        }
                    updated_customers[new_company_name] = company

                renamed_quotes = []
                if (
                    edit_mode
                    and not old_contact_name
                    and new_company_name != old_company_name
                ):
                    for quote in self.quotes:
                        quote_customer = quote.get("customer")
                        if (
                            isinstance(quote_customer, dict)
                            and quote_customer.get("name") == old_company_name
                        ):
                            quote_customer["name"] = new_company_name
                            renamed_quotes.append(quote)
                try:
                    self.store.save_customers(updated_customers)
                    if renamed_quotes:
                        self.save_data()
                except OSError as exc:
                    for quote in renamed_quotes:
                        quote["customer"]["name"] = old_company_name
                    if renamed_quotes:
                        try:
                            self.store.save_customers(self.customers)
                        except OSError as rollback_exc:
                            messagebox.showerror(
                                "Save and rollback failed",
                                f"Could not save customer changes ({exc}) or restore the previous database ({rollback_exc}).",
                                parent=dialog,
                            )
                            return
                    messagebox.showerror(
                        "Save failed",
                        f"Could not save the customer database:\n{exc}",
                        parent=dialog,
                    )
                    return

                self.customers = updated_customers
                saved_contact = new_contact_name or None
                dialog.destroy()
                refresh_database(new_company_name, saved_contact)
                status_label.config(text=f"Saved changes for {new_company_name}.")

            def delete_customer():
                if self.show_changes_blocked(dialog):
                    return

                if old_contact_name:
                    prompt = f"Delete contact {old_contact_name} from {old_company_name}?"
                else:
                    prompt = f"Delete company {old_company_name} and all of its contacts?"
                if not messagebox.askyesno("Delete customer", prompt, parent=dialog):
                    return

                updated_customers = deepcopy(self.customers)
                if old_contact_name:
                    company = updated_customers.get(old_company_name)
                    if company is None or old_contact_name not in company.get("contacts", {}):
                        messagebox.showerror(
                            "Contact not found",
                            "The selected contact no longer exists. Refresh the database and try again.",
                            parent=dialog,
                        )
                        return
                    company["contacts"].pop(old_contact_name)
                else:
                    updated_customers.pop(old_company_name, None)
                try:
                    self.store.save_customers(updated_customers)
                except OSError as exc:
                    messagebox.showerror(
                        "Delete failed",
                        f"Could not update the customer database:\n{exc}",
                        parent=dialog,
                    )
                    return
                self.customers = updated_customers
                dialog.destroy()
                refresh_database()
                status_label.config(text=f"Deleted {old_contact_name or old_company_name}.")

            def delete_company():
                if self.show_changes_blocked(dialog):
                    return

                if not messagebox.askyesno(
                    "Delete company",
                    f"Delete {old_company_name} and all of its contacts?",
                    parent=dialog,
                ):
                    return

                updated_customers = deepcopy(self.customers)
                updated_customers.pop(old_company_name, None)
                try:
                    self.store.save_customers(updated_customers)
                except OSError as exc:
                    messagebox.showerror(
                        "Delete failed",
                        f"Could not update the customer database:\n{exc}",
                        parent=dialog,
                    )
                    return
                self.customers = updated_customers
                dialog.destroy()
                refresh_database()
                status_label.config(text=f"Deleted company: {old_company_name}")

            buttons = tk.Frame(dialog)
            buttons.grid(row=5, column=0, columnspan=2, sticky="ew", padx=8, pady=10)
            tk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=4)
            tk.Button(
                buttons,
                text="Save",
                command=save_customer,
                bg="#4CAF50",
                fg="white",
            ).pack(side=tk.RIGHT, padx=4)
            if edit_mode:
                tk.Button(buttons, text="Delete", command=delete_customer).pack(side=tk.LEFT, padx=4)
                if old_contact_name:
                    tk.Button(
                        buttons,
                        text="Delete Company",
                        command=delete_company,
                    ).pack(side=tk.LEFT, padx=4)

            self.bind_enter_to_next(
                    company_entry,
                    contact_entry,
                    address_entry,
                    phone_entry,
                    email_entry,
            )
            company_entry.focus_set()

        def add_contact_to_selected_company():
            selected_rows = database_tree.selection()
            if not selected_rows:
                messagebox.showinfo(
                    "Select a company",
                    "Select a company in the customer database before adding a contact.",
                    parent=window,
                )
                return
            values = database_tree.item(selected_rows[0], "values")[:len(columns)]
            company_name = values[0]
            company = self.customers.get(company_name)
            if company is None:
                messagebox.showerror(
                    "Company not found",
                    "The selected company no longer exists. Refresh the database and try again.",
                    parent=window,
                )
                return
            open_customer_form(
                "add_contact",
                (company_name, "", company.get("address", ""), "", ""),
            )

        def edit_selected_row(event):
            row = database_tree.identify_row(event.y)
            if not row:
                return
            database_tree.selection_set(row)
            values = database_tree.item(row, "values")[:len(columns)]
            open_customer_form("edit", values)
            return "break"

        database_tree.bind("<Double-1>", edit_selected_row)
        refresh_database()

    def open_supplier_database(self):
        window = tk.Toplevel(self.root)
        window.title("Supplier Database")
        window.geometry("760x600")
        self.maximize_window(window)
        window.transient(self.root)

        buttons = tk.Frame(window, bg="#E2E8F0")
        buttons.pack(side=tk.TOP, fill=tk.X, padx=12, pady=6)
        tk.Button(
            buttons,
            text="+",
            command=lambda: open_supplier_form(),
            width=3,
            font=("Arial", 14, "bold"),
        ).pack(side=tk.LEFT, padx=4, pady=4)
        tk.Label(buttons, text="Double-click a row to edit").pack(side=tk.LEFT, padx=6)

        table_frame = tk.Frame(window)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        supplier_list = GridTreeview(
            table_frame,
            columns=("name", "address", "contact"),
            show="tree headings",
        )
        supplier_list.heading("#0", text="Line")
        supplier_list.column("#0", width=55, anchor=tk.CENTER, stretch=False)
        supplier_list.heading("name", text="Name")
        supplier_list.heading("address", text="Address")
        supplier_list.heading("contact", text="Contact")
        supplier_list.column("name", width=190)
        supplier_list.column("address", width=300)
        supplier_list.column("contact", width=200)
        supplier_scrollbar = ttk.Scrollbar(
            table_frame,
            orient=tk.VERTICAL,
            command=supplier_list.yview,
        )
        supplier_list.configure(yscrollcommand=supplier_scrollbar.set)
        supplier_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        supplier_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        status_label = tk.Label(
            window,
            text="Use + to add a supplier, or double-click a row to edit.",
            anchor=tk.W,
        )
        status_label.pack(fill=tk.X, padx=12, pady=(0, 8))

        def refresh_suppliers(select_name=None):
            for row in supplier_list.get_children():
                supplier_list.delete(row)
            for line_number, (name, details) in enumerate(
                sorted(self.suppliers.items(), key=lambda item: item[0].casefold()),
                start=1,
            ):
                row = supplier_list.insert(
                    "",
                    tk.END,
                    text=str(line_number),
                    values=(name, details.get("address", ""), details.get("contact", "")),
                )
                if name == select_name:
                    supplier_list.selection_set(row)
                    supplier_list.focus(row)
                    supplier_list.see(row)

        def open_supplier_form(supplier=None):
            if self.show_changes_blocked(window):
                return

            old_name = supplier[0] if supplier else None
            address = supplier[1] if supplier else ""
            contact = supplier[2] if supplier else ""
            edit_mode = old_name is not None

            dialog = tk.Toplevel(window)
            dialog.title("Edit Supplier" if edit_mode else "Add Supplier")
            dialog.geometry("520x250")
            dialog.transient(window)
            dialog.grab_set()
            dialog.columnconfigure(1, weight=1)

            tk.Label(dialog, text="Name:").grid(row=0, column=0, sticky="e", padx=8, pady=7)
            supplier_name_entry = tk.Entry(dialog)
            supplier_name_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=7)
            self.capitalize_words_on_focus_out(supplier_name_entry)
            if old_name:
                supplier_name_entry.insert(0, old_name)

            tk.Label(dialog, text="Address:").grid(row=1, column=0, sticky="ne", padx=8, pady=7)
            supplier_address_entry = tk.Text(dialog, height=3, wrap=tk.WORD)
            supplier_address_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=7)
            supplier_address_entry.insert("1.0", address)
            self.capitalize_words_on_focus_out(supplier_address_entry)

            tk.Label(dialog, text="Contact:").grid(row=2, column=0, sticky="e", padx=8, pady=7)
            supplier_contact_entry = tk.Entry(dialog)
            supplier_contact_entry.grid(row=2, column=1, sticky="ew", padx=8, pady=7)
            supplier_contact_entry.insert(0, contact)
            self.capitalize_words_on_focus_out(supplier_contact_entry)

            def save_supplier():
                if self.show_changes_blocked(dialog):
                    return

                supplier_name = supplier_name_entry.get().strip()
                if not supplier_name:
                    messagebox.showwarning(
                        "Supplier required",
                        "Enter a supplier name.",
                        parent=dialog,
                    )
                    return
                if supplier_name != old_name and supplier_name in self.suppliers:
                    messagebox.showerror(
                        "Supplier already exists",
                        f"A supplier named {supplier_name} already exists.",
                        parent=dialog,
                    )
                    return

                updated_suppliers = dict(self.suppliers)
                if edit_mode:
                    if old_name not in updated_suppliers:
                        messagebox.showerror(
                            "Supplier not found",
                            "The selected supplier no longer exists. Refresh the database and try again.",
                            parent=dialog,
                        )
                        return
                    updated_suppliers.pop(old_name)
                updated_suppliers[supplier_name] = {
                    "address": supplier_address_entry.get("1.0", tk.END).strip(),
                    "contact": supplier_contact_entry.get().strip(),
                }

                renamed_items = []
                if edit_mode and old_name != supplier_name:
                    for quote in self.quotes:
                        for item in quote.get("items", []):
                            if item.get("supplier") == old_name:
                                item["supplier"] = supplier_name
                                renamed_items.append(item)
                try:
                    self.store.save_suppliers(updated_suppliers)
                    if renamed_items:
                        self.save_data()
                except OSError as exc:
                    for item in renamed_items:
                        item["supplier"] = old_name
                    if renamed_items:
                        try:
                            self.store.save_suppliers(self.suppliers)
                        except OSError as rollback_exc:
                            messagebox.showerror(
                                "Save and rollback failed",
                                f"Could not save supplier changes ({exc}) or restore the previous database ({rollback_exc}).",
                                parent=dialog,
                            )
                            return
                    messagebox.showerror(
                        "Save failed",
                        f"Could not save the supplier database:\n{exc}",
                        parent=dialog,
                    )
                    return

                self.suppliers = updated_suppliers
                dialog.destroy()
                refresh_suppliers(supplier_name)
                status_label.config(text=f"Saved supplier: {supplier_name}")

            def delete_supplier():
                if self.show_changes_blocked(dialog):
                    return

                if not messagebox.askyesno(
                    "Delete supplier",
                    f"Delete {old_name} from the supplier database?",
                    parent=dialog,
                ):
                    return
                updated_suppliers = dict(self.suppliers)
                if old_name not in updated_suppliers:
                    messagebox.showerror(
                        "Supplier not found",
                        "The selected supplier no longer exists. Refresh the database and try again.",
                        parent=dialog,
                    )
                    return
                updated_suppliers.pop(old_name)
                try:
                    self.store.save_suppliers(updated_suppliers)
                except OSError as exc:
                    messagebox.showerror(
                        "Delete failed",
                        f"Could not save the supplier database:\n{exc}",
                        parent=dialog,
                    )
                    return
                self.suppliers = updated_suppliers
                dialog.destroy()
                refresh_suppliers()
                status_label.config(text=f"Deleted supplier: {old_name}")

            form_buttons = tk.Frame(dialog)
            form_buttons.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=10)
            tk.Button(form_buttons, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=4)
            tk.Button(
                form_buttons,
                text="Save",
                command=save_supplier,
                bg="#4CAF50",
                fg="white",
            ).pack(side=tk.RIGHT, padx=4)
            if edit_mode:
                tk.Button(form_buttons, text="Delete", command=delete_supplier).pack(side=tk.LEFT, padx=4)
            self.bind_enter_to_next(
                supplier_name_entry,
                supplier_address_entry,
                supplier_contact_entry,
            )
            supplier_name_entry.focus_set()

        def edit_supplier_on_double_click(event):
            row = supplier_list.identify_row(event.y)
            if not row:
                return
            values = supplier_list.item(row, "values")[:3]
            open_supplier_form(values)
            return "break"

        supplier_list.bind("<Double-1>", edit_supplier_on_double_click)
        refresh_suppliers()
        return window

    def open_settings_window(self):
        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.geometry("560x620")
        win.resizable(False, False)
        win.grab_set()
        win.columnconfigure(0, weight=1)

        main_settings = (
            ("VAT_Rate", "VAT Rate (%):", float),
            ("Starting_Quote_No", "Starting Quote No.:", int),
            ("Starting_Order_No", "Orders Start No.:", int),
            ("Starting_Delivery_Note_No", "Starting Delivery Note No.:", int),
        )

        general_frame = tk.LabelFrame(
            win,
            text="General",
            padx=14,
            pady=10,
            font=("Arial", 10, "bold"),
        )
        general_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        general_frame.columnconfigure(1, weight=1)

        entries = {}
        for row, (key, label_text, _) in enumerate(main_settings):
            tk.Label(general_frame, text=label_text, anchor=tk.W).grid(
                row=row,
                column=0,
                padx=(4, 16),
                pady=8,
                sticky="w",
            )
            ent = tk.Entry(general_frame, width=18, justify=tk.RIGHT)
            ent.insert(0, str(self.settings.get(key, "")))
            ent.grid(row=row, column=1, padx=4, pady=8, sticky="e")
            self.clear_zero_on_click(ent)
            entries[key] = ent
        self.bind_enter_to_next(*entries.values())

        end_date_frame = tk.Frame(general_frame)
        end_date_frame.grid(
            row=len(main_settings),
            column=0,
            columnspan=2,
            sticky="ew",
            padx=4,
            pady=(8, 2),
        )
        end_date_frame.columnconfigure(1, weight=1)
        tk.Label(end_date_frame, text="Software End Date:", anchor=tk.W).grid(
            row=0,
            column=0,
            padx=(0, 12),
            sticky="w",
        )
        end_date_value = tk.StringVar()

        def update_end_date_display():
            raw_end_date = str(self.settings.get("Software_End_Date", "")).strip()
            if not raw_end_date:
                end_date_value.set("Not set")
                return
            try:
                end_datetime = _parse_software_end_datetime(raw_end_date)
                end_date_value.set(end_datetime.strftime("%d.%m.%Y %H:%M"))
            except ValueError:
                end_date_value.set(raw_end_date)

        tk.Label(
            end_date_frame,
            textvariable=end_date_value,
            anchor=tk.W,
            fg="#334155",
        ).grid(row=0, column=1, sticky="ew")

        def open_admin_settings():
            pin = simpledialog.askstring(
                "Admin",
                "Enter admin PIN:",
                show="*",
                parent=win,
            )
            if pin is None:
                return
            if pin != "161100":
                messagebox.showerror("Access denied", "Incorrect admin PIN.", parent=win)
                return

            admin_window = tk.Toplevel(win)
            admin_window.title("Admin Settings")
            admin_window.geometry("480x230")
            admin_window.resizable(False, False)
            admin_window.transient(win)
            admin_window.grab_set()
            admin_window.columnconfigure(1, weight=1)

            tk.Label(admin_window, text="Software End Date:").grid(
                row=0,
                column=0,
                padx=12,
                pady=16,
                sticky="e",
            )
            end_date_entry = tk.Entry(admin_window, width=18, justify=tk.CENTER)
            end_date_entry.grid(row=0, column=1, padx=6, pady=16, sticky="ew")
            end_time_var = tk.StringVar(value="23:59")
            current_end_date = str(
                self.settings.get("Software_End_Date", "")
            ).strip()
            if current_end_date:
                try:
                    current_end_datetime = _parse_software_end_datetime(
                        current_end_date
                    )
                    end_time_var.set(current_end_datetime.strftime("%H:%M"))
                    current_end_date = current_end_datetime.strftime("%d.%m.%Y")
                except ValueError:
                    pass
                end_date_entry.insert(0, current_end_date)

            tk.Label(admin_window, text="End time (HH:MM):").grid(
                row=1,
                column=0,
                padx=12,
                pady=8,
                sticky="e",
            )
            end_time_entry = tk.Entry(
                admin_window,
                width=10,
                justify=tk.CENTER,
                textvariable=end_time_var,
            )
            end_time_entry.grid(row=1, column=1, padx=6, pady=8, sticky="w")

            def choose_end_date():
                try:
                    initial_date = datetime.strptime(
                        end_date_entry.get().strip(), "%d.%m.%Y"
                    ).date()
                except ValueError:
                    initial_date = date.today()

                def set_end_date(selected_date):
                    end_date_entry.delete(0, tk.END)
                    end_date_entry.insert(0, selected_date.strftime("%d.%m.%Y"))

                self.open_required_date_calendar(
                    admin_window,
                    initial_date,
                    set_end_date,
                )

            tk.Button(
                admin_window,
                text="Choose date...",
                command=choose_end_date,
            ).grid(row=0, column=2, padx=(0, 12), pady=16)
            tk.Label(
                admin_window,
                text="Leave date blank to remove the read-only limit.",
                fg="#64748B",
            ).grid(row=2, column=0, columnspan=3, padx=12, sticky="w")

            def save_end_date():
                date_text = end_date_entry.get().strip()
                end_date_iso = ""
                if date_text:
                    try:
                        end_date = datetime.strptime(
                            date_text,
                            "%d.%m.%Y",
                        ).date()
                    except ValueError:
                        messagebox.showerror(
                            "Invalid date",
                            "Enter a valid date in DD.MM.YYYY format or choose it from the calendar.",
                            parent=admin_window,
                        )
                        return
                    try:
                        end_time = datetime.strptime(
                            end_time_var.get().strip(),
                            "%H:%M",
                        ).time()
                    except ValueError:
                        messagebox.showerror(
                            "Invalid time",
                            "Enter a valid end time in HH:MM format (24-hour clock).",
                            parent=admin_window,
                        )
                        return
                    end_date_iso = datetime.combine(
                        end_date,
                        end_time,
                    ).strftime("%Y-%m-%d %H:%M")

                previous_value = self.settings.get("Software_End_Date")
                self.settings["Software_End_Date"] = end_date_iso
                try:
                    self.save_settings()
                except OSError as exc:
                    if previous_value is None:
                        self.settings.pop("Software_End_Date", None)
                    else:
                        self.settings["Software_End_Date"] = previous_value
                    messagebox.showerror(
                        "Save failed",
                        f"Could not save Software End Date:\n{exc}",
                        parent=admin_window,
                    )
                    return
                update_end_date_display()
                admin_window.destroy()

            tk.Button(
                admin_window,
                text="Save",
                command=save_end_date,
                bg="#2563EB",
                fg="white",
                relief=tk.FLAT,
                padx=16,
                pady=6,
            ).grid(row=3, column=0, columnspan=3, pady=12)

        tk.Button(
            end_date_frame,
            text="Admin",
            command=open_admin_settings,
            cursor="hand2",
        ).grid(row=0, column=2, padx=(8, 0))
        update_end_date_display()

        def open_stats_from_settings():
            win.grab_release()
            report = self.open_order_stats(parent=win)
            if report is None:
                win.grab_set()

        tools_frame = tk.LabelFrame(
            win,
            text="More Settings",
            padx=14,
            pady=10,
            font=("Arial", 10, "bold"),
        )
        tools_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        tools_frame.columnconfigure(0, weight=1)
        for row, (label, command) in enumerate(
            (
                ("Links", lambda: self.open_links_settings_window(win)),
                ("Rates", lambda: self.open_rates_settings_window(win)),
                ("Stats", open_stats_from_settings),
                ("Company Details", lambda: self.open_company_details_window(win)),
                ("PDF Layout Generator", lambda: self.open_pdf_layout_editor(win)),
            )
        ):
            button = tk.Button(
                tools_frame,
                text=label,
                command=command,
                anchor=tk.W,
                padx=12,
                pady=7,
                relief=tk.GROOVE,
                cursor="hand2",
                font=("Arial", 9),
            )
            button.grid(row=row, column=0, padx=4, pady=4, sticky="ew")

        def save_settings():
            if self.show_changes_blocked(win):
                return

            new_settings = {}
            for key, label_text, value_type in main_settings:
                try:
                    value = entries[key].get().strip() or "0"
                    if value_type is float:
                        new_settings[key] = float(value.replace(",", "."))
                    else:
                        new_settings[key] = int(value)
                except ValueError:
                    messagebox.showerror("Error", f"Invalid value for {label_text}", parent=win)
                    return

            self.settings.update(new_settings)
            try:
                self.save_settings()
            except OSError as exc:
                messagebox.showerror("Save failed", f"Could not save settings:\n{exc}", parent=win)
                return
            self.refresh_list()
            messagebox.showinfo("Success", "Settings saved successfully.", parent=win)
            win.destroy()

        tk.Button(
            win,
            text="Save Settings",
            command=save_settings,
            bg="#2563EB",
            fg="white",
            activebackground="#1D4ED8",
            activeforeground="white",
            relief=tk.FLAT,
            borderwidth=0,
            padx=18,
            pady=9,
            cursor="hand2",
            font=("Arial", 10, "bold"),
        ).grid(row=2, column=0, pady=(8, 16))
        win.update_idletasks()
        screen_width = win.winfo_screenwidth()
        screen_height = win.winfo_screenheight()
        window_width = min(max(560, win.winfo_reqwidth() + 40), screen_width - 40)
        window_height = min(max(480, win.winfo_reqheight() + 30), screen_height - 80)
        window_x = max(0, (screen_width - window_width) // 2)
        window_y = max(0, (screen_height - window_height) // 2)
        win.geometry(
            f"{window_width}x{window_height}+{window_x}+{window_y}"
        )

    def open_pdf_layout_editor(self, parent):
        layouts = get_layouts(self.settings)
        window = tk.Toplevel(parent)
        window.title("PDF Layout Generator")
        window.geometry("1120x780")
        window.minsize(980, 700)
        window.transient(parent)
        window.grab_set()

        document_types = {
            "Quote": "quote",
            "Delivery Note": "delivery_note",
            "Job Card": "job_card",
        }
        selected_document = tk.StringVar(value="Quote")
        current_type = {"value": "quote"}
        selected_element = {"index": None}
        drag_state = {"index": None, "x": 0, "y": 0}

        toolbar = tk.Frame(window, padx=12, pady=8)
        toolbar.pack(fill=tk.X)
        tk.Label(toolbar, text="Document:").pack(side=tk.LEFT, padx=(0, 8))
        document_choice = ttk.Combobox(
            toolbar,
            textvariable=selected_document,
            values=tuple(document_types),
            state="readonly",
            width=20,
        )
        document_choice.pack(side=tk.LEFT)
        tk.Label(
            toolbar,
            text="Drag fields on the page, or edit their exact position and style.",
            fg="#475569",
        ).pack(side=tk.LEFT, padx=14)

        body = tk.Frame(window)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        preview_panel = tk.Frame(body, bg="#E2E8F0")
        preview_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        canvas = tk.Canvas(
            preview_panel,
            bg="#E2E8F0",
            highlightthickness=0,
        )
        canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        controls = tk.Frame(body, width=340)
        controls.pack(side=tk.RIGHT, fill=tk.Y)
        controls.pack_propagate(False)
        catalog_frame = tk.LabelFrame(controls, text="Add information", padx=8, pady=8)
        catalog_frame.pack(fill=tk.X, pady=(0, 8))
        catalog_choice = ttk.Combobox(catalog_frame, state="readonly", width=33)
        catalog_choice.pack(fill=tk.X, pady=(0, 6))
        add_field_button = tk.Button(catalog_frame, text="Add field", cursor="hand2")
        add_field_button.pack(fill=tk.X)

        element_frame = tk.LabelFrame(controls, text="Selected field", padx=8, pady=8)
        element_frame.pack(fill=tk.X, pady=(0, 8))
        element_frame.columnconfigure(1, weight=1)
        element_list = tk.Listbox(element_frame, height=7, exportselection=False)
        element_list.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        properties = {}
        for row, (key, label) in enumerate(
            (
                ("label", "Label / text"),
                ("x", "X position (mm)"),
                ("y", "Y position (mm)"),
                ("w", "Width (mm)"),
                ("h", "Height (mm)"),
                ("font_size", "Font size"),
            ),
            start=1,
        ):
            tk.Label(element_frame, text=label, anchor=tk.W).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 8),
                pady=3,
            )
            entry = tk.Entry(element_frame)
            entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
            properties[key] = entry

        tk.Label(element_frame, text="Font").grid(row=7, column=0, sticky="w", pady=3)
        font_choice = ttk.Combobox(
            element_frame,
            values=("Arial", "Helvetica", "Times", "Courier"),
            state="readonly",
            width=12,
        )
        font_choice.grid(row=7, column=1, columnspan=2, sticky="ew", pady=3)
        tk.Label(element_frame, text="Style").grid(row=8, column=0, sticky="w", pady=3)
        style_choice = ttk.Combobox(
            element_frame,
            values=("", "B", "I", "BI"),
            state="readonly",
            width=12,
        )
        style_choice.grid(row=8, column=1, columnspan=2, sticky="ew", pady=3)
        visible_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            element_frame,
            text="Visible in PDF",
            variable=visible_var,
            command=lambda: update_selected({"visible": visible_var.get()}),
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=4)
        color_button = tk.Button(element_frame, text="Text color")
        color_button.grid(row=9, column=2, sticky="ew", padx=(4, 0), pady=4)
        apply_button = tk.Button(element_frame, text="Apply changes")
        apply_button.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        remove_button = tk.Button(element_frame, text="Remove field")
        remove_button.grid(row=10, column=2, sticky="ew", padx=(4, 0), pady=(6, 0))
        table_columns_frame = tk.LabelFrame(
            element_frame,
            text="Table columns (select fields)",
            padx=4,
            pady=4,
        )
        table_columns_frame.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        table_columns_list = tk.Listbox(
            table_columns_frame,
            height=5,
            selectmode=tk.MULTIPLE,
            exportselection=False,
        )
        table_columns_list.pack(fill=tk.X, expand=True)
        apply_table_columns_button = tk.Button(
            table_columns_frame,
            text="Apply table columns",
        )
        apply_table_columns_button.pack(fill=tk.X, pady=(4, 0))
        table_columns_frame.grid_remove()

        status = tk.Label(window, text="Preview is a layout guide; final text wraps to the configured field width.", anchor=tk.W)
        status.pack(fill=tk.X, padx=16, pady=(0, 4))
        actions = tk.Frame(window, padx=12, pady=8)
        actions.pack(fill=tk.X)
        tk.Button(actions, text="Reset document layout", command=lambda: reset_layout(), cursor="hand2").pack(
            side=tk.LEFT
        )
        tk.Button(
            actions,
            text="Preview PDF",
            command=lambda: preview_pdf(),
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=10)
        tk.Button(actions, text="Cancel", command=window.destroy, cursor="hand2").pack(
            side=tk.RIGHT, padx=(6, 0)
        )
        tk.Button(
            actions,
            text="Save layouts",
            command=lambda: save_layouts(),
            bg="#2563EB",
            fg="white",
            activebackground="#1D4ED8",
            activeforeground="white",
            relief=tk.FLAT,
            padx=16,
            pady=7,
            cursor="hand2",
            font=("Arial", 9, "bold"),
        ).pack(side=tk.RIGHT)

        page_geometry = {"x": 0, "y": 0, "scale": 1}

        def current_elements():
            return layouts[current_type["value"]]

        def refresh_list():
            element_list.delete(0, tk.END)
            for element in current_elements():
                field_labels = dict(FIELD_CATALOG[current_type["value"]])
                label = field_labels.get(element["field"], element["field"])
                state = "" if element.get("visible", True) else " [hidden]"
                element_list.insert(tk.END, f"{label}{state}")
            if selected_element["index"] is not None and current_elements():
                selected_element["index"] = min(
                    selected_element["index"],
                    len(current_elements()) - 1,
                )
                element_list.selection_set(selected_element["index"])
                load_properties()
            else:
                selected_element["index"] = None
                clear_properties()
            draw_preview()

        def update_add_button_text(event=None):
            selected_label = catalog_choice.get()
            selected_field = next(
                (
                    field
                    for field, label in FIELD_CATALOG[current_type["value"]]
                    if label == selected_label
                ),
                None,
            )
            add_field_button.configure(
                text="Add items table" if selected_field == "items_table" else "Add field"
            )

        def clear_properties():
            for entry in properties.values():
                entry.delete(0, tk.END)
            font_choice.set("")
            style_choice.set("")
            visible_var.set(False)
            color_button.configure(bg=element_frame.cget("bg"))

        def load_properties():
            index = selected_element["index"]
            if index is None or index >= len(current_elements()):
                clear_properties()
                table_columns_frame.grid_remove()
                return
            element = current_elements()[index]
            for key, entry in properties.items():
                entry.delete(0, tk.END)
                entry.insert(0, str(element.get(key, "")))
            font_choice.set(element.get("font", "Arial"))
            style_choice.set(element.get("style", ""))
            visible_var.set(bool(element.get("visible", True)))
            color_button.configure(bg=element.get("color", "#111827"))
            if element.get("field") == "items_table":
                table_columns_frame.grid()
                table_columns_list.delete(0, tk.END)
                column_catalog = TABLE_COLUMN_CATALOG[current_type["value"]]
                selected_columns = element.get(
                    "table_columns",
                    DEFAULT_TABLE_COLUMNS[current_type["value"]],
                )
                for column, label in column_catalog:
                    table_columns_list.insert(tk.END, label)
                    if column in selected_columns:
                        table_columns_list.selection_set(tk.END)
            else:
                table_columns_frame.grid_remove()

        def draw_preview():
            canvas.delete("all")
            canvas.update_idletasks()
            available_width = max(300, canvas.winfo_width() - 36)
            available_height = max(400, canvas.winfo_height() - 36)
            scale = min(available_width / PAGE_WIDTH, available_height / PAGE_HEIGHT)
            page_width_px = PAGE_WIDTH * scale
            page_height_px = PAGE_HEIGHT * scale
            page_x = (canvas.winfo_width() - page_width_px) / 2
            page_y = (canvas.winfo_height() - page_height_px) / 2
            page_geometry.update(x=page_x, y=page_y, scale=scale)
            canvas.create_rectangle(
                page_x,
                page_y,
                page_x + page_width_px,
                page_y + page_height_px,
                fill="white",
                outline="#94A3B8",
            )
            catalog = dict(FIELD_CATALOG[current_type["value"]])
            for index, element in enumerate(current_elements()):
                x = page_x + float(element.get("x", 0)) * scale
                y = page_y + float(element.get("y", 0)) * scale
                width = float(element.get("w", 1)) * scale
                height = float(element.get("h", 1)) * scale
                selected = index == selected_element["index"]
                color = element.get("color", "#111827")
                outline = "#2563EB" if selected else "#94A3B8"
                canvas.create_rectangle(
                    x,
                    y,
                    x + width,
                    y + height,
                    fill="#EFF6FF" if selected else "#F8FAFC",
                    outline=outline,
                    width=2 if selected else 1,
                    tags=(f"layout:{index}",),
                )
                label = element.get("label") or catalog.get(element["field"], element["field"])
                if element["field"] == "items_table":
                    table_columns = element.get(
                        "table_columns",
                        DEFAULT_TABLE_COLUMNS[current_type["value"]],
                    )
                    column_labels = dict(TABLE_COLUMN_CATALOG[current_type["value"]])
                    visible_columns = [
                        column for column in table_columns if column in column_labels
                    ]
                    canvas.create_text(
                        x + 4,
                        y + 2,
                        text=label,
                        anchor="nw",
                        fill=color,
                        font=("Arial", max(6, min(12, int(element.get("font_size", 10) * scale * 0.75)))),
                        tags=(f"layout:{index}",),
                    )
                    grid_y = y + min(height * 0.28, 16 * scale)
                    grid_height = max(3, (height - (grid_y - y)) / 3)
                    if visible_columns:
                        column_width = width / len(visible_columns)
                        for row_index in range(3):
                            for column_index, column in enumerate(visible_columns):
                                cell_x = x + column_index * column_width
                                cell_y = grid_y + row_index * grid_height
                                canvas.create_rectangle(
                                    cell_x,
                                    cell_y,
                                    cell_x + column_width,
                                    cell_y + grid_height,
                                    fill="#E2E8F0" if row_index == 0 else "white",
                                    outline="#94A3B8",
                                    tags=(f"layout:{index}",),
                                )
                                if row_index == 0:
                                    canvas.create_text(
                                        cell_x + 2,
                                        cell_y + 2,
                                        text=column_labels[column],
                                        anchor="nw",
                                        fill=color,
                                        font=("Arial", max(5, min(9, int(7 * scale)))),
                                        width=max(4, column_width - 4),
                                        tags=(f"layout:{index}",),
                                    )
                    continue
                sample = "" if element["field"] == "company_logo" else f"\n{label}"
                canvas.create_text(
                    x + 4,
                    y + 3,
                    text=sample.strip(),
                    anchor="nw",
                    fill=color,
                    font=("Arial", max(6, min(12, int(element.get("font_size", 10) * scale * 0.75)))),
                    width=max(5, width - 8),
                    tags=(f"layout:{index}",),
                )
            canvas.create_text(
                page_x + 6,
                page_y + page_height_px + 8,
                text="A4 • 210 × 297 mm",
                anchor="nw",
                fill="#475569",
                font=("Arial", 8),
            )

        def update_selected(changes):
            index = selected_element["index"]
            if index is None or index >= len(current_elements()):
                return
            current_elements()[index].update(changes)
            refresh_list()

        def apply_properties():
            index = selected_element["index"]
            if index is None or index >= len(current_elements()):
                return
            try:
                x = float(properties["x"].get())
                y = float(properties["y"].get())
                width = float(properties["w"].get())
                height = float(properties["h"].get())
                font_size = int(properties["font_size"].get())
                if width <= 0 or height <= 0 or not 5 <= font_size <= 36:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Invalid layout value",
                    "Enter valid positions and positive dimensions. Font size must be between 5 and 36.",
                    parent=window,
                )
                return
            element = current_elements()[index]
            element.update(
                {
                    "label": properties["label"].get(),
                    "x": max(0, min(PAGE_WIDTH - 1, x)),
                    "y": max(0, min(PAGE_HEIGHT - 1, y)),
                    "w": min(PAGE_WIDTH, width),
                    "h": min(PAGE_HEIGHT, height),
                    "font_size": font_size,
                    "font": font_choice.get() or "Arial",
                    "style": style_choice.get(),
                    "visible": visible_var.get(),
                }
            )
            refresh_list()

        def choose_color():
            index = selected_element["index"]
            if index is None:
                return
            initial = current_elements()[index].get("color", "#111827")
            color = colorchooser.askcolor(initialcolor=initial, parent=window)[1]
            if color:
                current_elements()[index]["color"] = color
                color_button.configure(bg=color)
                draw_preview()

        def add_field():
            field_name = catalog_choice.get()
            options = dict(FIELD_CATALOG[current_type["value"]])
            if field_name not in options:
                return
            field = next(key for key, label in FIELD_CATALOG[current_type["value"]] if label == field_name)
            index = len(current_elements())
            current_elements().append(
                {
                    "id": f"{field}-{index + 1}",
                    "field": field,
                    "label": "",
                    "x": 15,
                    "y": min(245, 15 + index * 8),
                    "w": 120,
                    "h": 18,
                    "font_size": 10,
                    "font": "Arial",
                    "style": "",
                    "color": "#111827",
                    "visible": True,
                    **(
                        {
                            "table_columns": list(
                                DEFAULT_TABLE_COLUMNS[current_type["value"]]
                            )
                        }
                        if field == "items_table"
                        else {}
                    ),
                }
            )
            selected_element["index"] = index
            refresh_list()

        def apply_table_columns():
            index = selected_element["index"]
            if index is None or index >= len(current_elements()):
                return
            element = current_elements()[index]
            if element.get("field") != "items_table":
                return
            selected_indices = table_columns_list.curselection()
            if not selected_indices:
                messagebox.showwarning(
                    "Table columns required",
                    "Select at least one field for the table.",
                    parent=window,
                )
                return
            column_catalog = TABLE_COLUMN_CATALOG[current_type["value"]]
            element["table_columns"] = [
                column_catalog[column_index][0]
                for column_index in selected_indices
            ]
            refresh_list()

        def remove_field():
            index = selected_element["index"]
            if index is None:
                return
            current_elements().pop(index)
            selected_element["index"] = min(index, len(current_elements()) - 1) if current_elements() else None
            refresh_list()

        def reset_layout():
            if not messagebox.askyesno(
                "Reset layout",
                "Restore the default layout for this document?",
                parent=window,
            ):
                return
            layouts[current_type["value"]] = deepcopy(DEFAULT_LAYOUTS[current_type["value"]])
            selected_element["index"] = None
            refresh_catalog()
            refresh_list()

        def save_layouts():
            if self.show_changes_blocked(window):
                return

            previous_layouts = self.settings.get("PDF_Layouts")
            self.settings["PDF_Layouts"] = deepcopy(layouts)
            try:
                self.save_settings()
            except OSError as exc:
                if previous_layouts is None:
                    self.settings.pop("PDF_Layouts", None)
                else:
                    self.settings["PDF_Layouts"] = previous_layouts
                messagebox.showerror(
                    "Save failed",
                    f"Could not save PDF layouts:\n{exc}",
                    parent=window,
                )
                return
            messagebox.showinfo("Success", "PDF layouts saved.", parent=window)

        def preview_pdf():
            preview_items = [
                {
                    "name": "Sample Component",
                    "req_date": date.today().isoformat(),
                    "drawing_number": "DWG-1001",
                    "revision": "A",
                    "quantity": 5,
                    "material": "Aluminium",
                    "material_cost": 12.5,
                    "supplier": "Sample Supplier",
                    "mct_number": "MCT-1001",
                    "cast": "CAST-1001",
                    "operations": [
                        {
                            "type": "Machining",
                            "time": 0.75,
                            "rate": 60.0,
                            "cost": 45.0,
                        },
                        {
                            "type": "Finishing",
                            "time": 0.25,
                            "rate": 45.0,
                            "cost": 11.25,
                        },
                    ],
                },
                {
                    "name": "Sample Bracket",
                    "req_date": date.today().isoformat(),
                    "drawing_number": "DWG-1002",
                    "revision": "B",
                    "quantity": 2,
                    "material": "Mild Steel",
                    "material_cost": 8.0,
                    "supplier": "Sample Supplier",
                    "mct_number": "MCT-1002",
                    "cast": "",
                    "operations": [
                        {
                            "type": "Cutting",
                            "time": 0.5,
                            "rate": 40.0,
                            "cost": 20.0,
                        },
                    ],
                },
            ]
            sample_data = {
                "number": "PREVIEW-001",
                "delivery_note_number": "DN-PREVIEW-001",
                "name": "PDF layout preview",
                "status": "order" if current_type["value"] != "quote" else "quote",
                "required_date": date.today().isoformat(),
                "customer_po_number": "PO-PREVIEW-001",
                "customer": {
                    "name": "Sample Customer Ltd",
                    "address": "10 Example Street\nExample Town",
                    "contact": "Alex Example",
                    "phone": "01234 567890",
                    "email": "alex@example.com",
                },
                "markup": 15,
                "discount": 5,
                "items": preview_items,
            }
            preview_directory = tempfile.mkdtemp(prefix="wyceny_pdf_preview_")
            preview_settings = deepcopy(self.settings)
            preview_settings["PDF_Layouts"] = deepcopy(layouts)
            preview_settings["Pdf_Output_Directory"] = preview_directory
            try:
                preview_path = generate_layout_document(
                    current_type["value"],
                    sample_data,
                    preview_settings,
                )
                os.startfile(preview_path)
            except (OSError, RuntimeError, ValueError) as exc:
                messagebox.showerror(
                    "PDF preview failed",
                    f"Could not create or open the PDF preview:\n{exc}",
                    parent=window,
                )

        def refresh_catalog():
            catalog_choice["values"] = tuple(
                label for _, label in FIELD_CATALOG[current_type["value"]]
            )
            catalog_choice.set("")
            update_add_button_text()

        def change_document(event=None):
            selected_element["index"] = None
            current_type["value"] = document_types[selected_document.get()]
            refresh_catalog()
            refresh_list()

        def select_element(event=None):
            selection = element_list.curselection()
            selected_element["index"] = selection[0] if selection else None
            load_properties()
            draw_preview()

        def canvas_to_mm(event):
            return (
                max(0, min(PAGE_WIDTH, (event.x - page_geometry["x"]) / page_geometry["scale"])),
                max(0, min(PAGE_HEIGHT, (event.y - page_geometry["y"]) / page_geometry["scale"])),
            )

        def start_drag(event):
            x, y = canvas_to_mm(event)
            closest = canvas.find_closest(event.x, event.y)
            tags = canvas.gettags(closest[0]) if closest else ()
            index = next(
                (int(tag.split(":", 1)[1]) for tag in tags if tag.startswith("layout:")),
                None,
            )
            if index is None or index >= len(current_elements()):
                return
            selected_element["index"] = index
            element = current_elements()[index]
            drag_state.update(
                index=index,
                x=x - float(element.get("x", 0)),
                y=y - float(element.get("y", 0)),
            )
            element_list.selection_clear(0, tk.END)
            element_list.selection_set(index)
            load_properties()
            draw_preview()

        def drag(event):
            index = drag_state["index"]
            if index is None or index >= len(current_elements()):
                return
            x, y = canvas_to_mm(event)
            element = current_elements()[index]
            element["x"] = max(0, min(PAGE_WIDTH - float(element.get("w", 1)), x - drag_state["x"]))
            element["y"] = max(0, min(PAGE_HEIGHT - float(element.get("h", 1)), y - drag_state["y"]))
            load_properties()
            draw_preview()

        def end_drag(event):
            drag_state["index"] = None

        element_list.bind("<<ListboxSelect>>", select_element)
        document_choice.bind("<<ComboboxSelected>>", change_document)
        add_field_button.configure(command=add_field)
        catalog_choice.bind("<<ComboboxSelected>>", update_add_button_text)
        apply_table_columns_button.configure(command=apply_table_columns)
        apply_button.configure(command=apply_properties)
        remove_button.configure(command=remove_field)
        color_button.configure(command=choose_color)
        canvas.bind("<Button-1>", start_drag)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", end_drag)
        canvas.bind("<Configure>", lambda event: draw_preview())
        refresh_catalog()
        refresh_list()

    def open_links_settings_window(self, parent):
        win = tk.Toplevel(parent)
        win.title("Links")
        win.geometry("620x240")
        win.transient(parent)
        win.grab_set()

        logo_path = tk.StringVar(value=self.settings.get("Logo_Path", ""))
        pdf_directory = tk.StringVar(value=self.settings.get("Pdf_Output_Directory", ""))
        tk.Label(win, text="Company Logo:").grid(row=0, column=0, padx=12, pady=12, sticky="e")
        logo_entry = tk.Entry(win, textvariable=logo_path, width=48)
        logo_entry.grid(
            row=0, column=1, padx=5, pady=12, sticky="ew"
        )

        def browse_logo():
            selected_path = filedialog.askopenfilename(
                parent=win,
                title="Select company logo",
                filetypes=[
                    ("Image files", "*.png *.jpg *.jpeg"),
                    ("PNG files", "*.png"),
                    ("JPEG files", "*.jpg *.jpeg"),
                ],
            )
            if selected_path:
                logo_path.set(selected_path)

        tk.Button(win, text="Browse...", command=browse_logo).grid(row=0, column=2, padx=5, pady=12)
        tk.Label(win, text="PDF Save Folder:").grid(row=1, column=0, padx=12, pady=12, sticky="e")
        pdf_directory_entry = tk.Entry(win, textvariable=pdf_directory, width=48)
        pdf_directory_entry.grid(
            row=1, column=1, padx=5, pady=12, sticky="ew"
        )
        self.bind_enter_to_next(logo_entry, pdf_directory_entry)

        def browse_pdf_directory():
            selected_directory = filedialog.askdirectory(
                parent=win,
                title="Select PDF save folder",
                initialdir=pdf_directory.get() or os.getcwd(),
                mustexist=True,
            )
            if selected_directory:
                pdf_directory.set(selected_directory)

        tk.Button(win, text="Browse...", command=browse_pdf_directory).grid(
            row=1, column=2, padx=5, pady=12
        )
        tk.Label(win, text="Logo formats: PNG, JPG, JPEG").grid(
            row=2, column=1, sticky="w", padx=5
        )

        def save_links():
            if self.show_changes_blocked(win):
                return

            selected_logo = logo_path.get().strip()
            if selected_logo and not os.path.isfile(selected_logo):
                messagebox.showerror("Invalid logo", "The selected logo file does not exist.", parent=win)
                return
            if selected_logo and os.path.splitext(selected_logo)[1].lower() not in (".png", ".jpg", ".jpeg"):
                messagebox.showerror("Invalid logo", "Choose a PNG or JPEG image.", parent=win)
                return

            selected_directory = pdf_directory.get().strip()
            if selected_directory and not os.path.isdir(selected_directory):
                messagebox.showerror(
                    "Invalid folder",
                    "The selected PDF save folder does not exist.",
                    parent=win,
                )
                return

            self.settings["Logo_Path"] = selected_logo
            self.settings["Pdf_Output_Directory"] = selected_directory
            try:
                self.save_settings()
            except OSError as exc:
                messagebox.showerror("Save failed", f"Could not save links:\n{exc}", parent=win)
                return
            self.refresh_app_logo()
            messagebox.showinfo("Success", "Links saved successfully.", parent=win)
            win.destroy()

        tk.Button(win, text="Save", command=save_links, bg="#2196F3", fg="white").grid(
            row=3, column=0, columnspan=3, pady=18
        )

    def open_rates_settings_window(self, parent):
        win = tk.Toplevel(parent)
        win.title("Rates - Operations")
        win.geometry("460x440")
        win.transient(parent)
        win.grab_set()

        non_operation_settings = {
            "VAT_Rate",
            "Starting_Quote_No",
            "Starting_Order_No",
            "Starting_Delivery_Note_No",
            "Logo_Path",
            "Pdf_Output_Directory",
            "Company_Name",
            "Company_Address",
            "Company_Postcode",
            "Company_Reg_No",
            "VAT_Reg_No",
            "Company_Phone_Landline",
            "Company_Phone_Mobile",
            "PDF_Layouts",
        }
        operation_rates = {
            key: value
            for key, value in self.settings.items()
            if key not in non_operation_settings
        }
        entries = {}
        operation_rows = tk.Frame(win)
        operation_rows.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        def add_operation_row(operation, rate):
            row = tk.Frame(operation_rows)
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=f"{operation} Rate:", width=28, anchor=tk.E).pack(
                side=tk.LEFT, padx=(0, 8)
            )
            entry = tk.Entry(row, width=12)
            entry.insert(0, str(rate))
            entry.pack(side=tk.LEFT)
            self.clear_zero_on_click(entry)
            self.bind_enter_to_next(entry)
            entries[operation] = entry

        for operation, rate in operation_rates.items():
            add_operation_row(operation, rate)

        add_frame = tk.LabelFrame(win, text="Add Operation")
        add_frame.pack(fill=tk.X, padx=12, pady=(4, 8))
        tk.Label(add_frame, text="Operation name:").grid(
            row=0, column=0, padx=8, pady=6, sticky="e"
        )
        new_operation_name = tk.Entry(add_frame, width=24)
        new_operation_name.grid(row=0, column=1, padx=8, pady=6, sticky="w")
        self.capitalize_words_on_focus_out(new_operation_name)
        tk.Label(add_frame, text="Rate (/h):").grid(
            row=1, column=0, padx=8, pady=6, sticky="e"
        )
        new_operation_rate = tk.Entry(add_frame, width=12)
        new_operation_rate.grid(row=1, column=1, padx=8, pady=6, sticky="w")
        self.bind_enter_to_next(new_operation_name, new_operation_rate)

        def save_rates():
            if self.show_changes_blocked(win):
                return

            new_rates = {}
            for operation, entry in entries.items():
                try:
                    value = entry.get().strip().replace(",", ".") or "0"
                    new_rates[operation] = float(value)
                except ValueError:
                    messagebox.showerror(
                        "Error",
                        f"Invalid rate for {operation}.",
                        parent=win,
                    )
                    return

            self.settings.update(new_rates)
            try:
                self.save_settings()
            except OSError as exc:
                messagebox.showerror("Save failed", f"Could not save operation rates:\n{exc}", parent=win)
                return
            self.refresh_list()
            messagebox.showinfo("Success", "Operation rates saved successfully.", parent=win)
            win.destroy()

        def add_operation():
            if self.show_changes_blocked(win):
                return

            operation = new_operation_name.get().strip()
            rate_text = new_operation_rate.get().strip().replace(",", ".")
            if not operation:
                messagebox.showwarning(
                    "Missing operation name",
                    "Enter a name for the new operation.",
                    parent=win,
                )
                return
            reserved_names = {
                str(key).casefold()
                for key in self.settings
                if key not in operation_rates
            }
            if operation.casefold() in reserved_names:
                messagebox.showerror(
                    "Invalid operation name",
                    "This name is reserved for an application setting.",
                    parent=win,
                )
                return
            if any(existing.casefold() == operation.casefold() for existing in entries):
                messagebox.showerror(
                    "Duplicate operation",
                    f"An operation named '{operation}' already exists.",
                    parent=win,
                )
                return
            try:
                rate = float(rate_text)
                if rate < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Invalid rate",
                    "Enter a non-negative numeric rate.",
                    parent=win,
                )
                return

            add_operation_row(operation, rate)
            new_operation_name.delete(0, tk.END)
            new_operation_rate.delete(0, tk.END)

        tk.Button(add_frame, text="Add", command=add_operation).grid(
            row=0, column=2, rowspan=2, padx=10, pady=6
        )
        tk.Button(
            win,
            text="Save Rates",
            command=save_rates,
            bg="#2196F3",
            fg="white",
        ).pack(pady=(4, 14))

    def open_company_details_window(self, parent):
        details_win = tk.Toplevel(parent)
        details_win.title("Company Details")
        details_win.geometry("500x460")
        details_win.transient(parent)
        details_win.grab_set()

        fields = {
            "Company_Name": tk.StringVar(value=self.settings.get("Company_Name", "")),
            "Company_Address": tk.StringVar(value=self.settings.get("Company_Address", "")),
            "Company_Postcode": tk.StringVar(value=self.settings.get("Company_Postcode", "")),
            "Company_Reg_No": tk.StringVar(value=self.settings.get("Company_Reg_No", "")),
            "VAT_Reg_No": tk.StringVar(value=self.settings.get("VAT_Reg_No", "")),
            "Company_Phone_Landline": tk.StringVar(value=self.settings.get("Company_Phone_Landline", "")),
            "Company_Phone_Mobile": tk.StringVar(value=self.settings.get("Company_Phone_Mobile", "")),
        }
        field_labels = (
            ("Company Name:", "Company_Name"),
            ("Address:", "Company_Address"),
            ("Post Code:", "Company_Postcode"),
            ("Company Reg. No.:", "Company_Reg_No"),
            ("Vat Reg. No.:", "VAT_Reg_No"),
            ("Landline Phone:", "Company_Phone_Landline"),
            ("Mobile Phone:", "Company_Phone_Mobile"),
        )
        company_entries = []
        for row, (label_text, key) in enumerate(field_labels):
            tk.Label(details_win, text=label_text).grid(
                row=row, column=0, padx=15, pady=8, sticky="e"
            )
            entry = tk.Entry(details_win, width=38, textvariable=fields[key])
            entry.grid(
                row=row, column=1, padx=10, pady=8, sticky="ew"
            )
            company_entries.append(entry)
            if key in ("Company_Name", "Company_Address"):
                self.capitalize_words_on_focus_out(entry)
        self.bind_enter_to_next(*company_entries)

        def save_company_details():
            if self.show_changes_blocked(details_win):
                return

            for key, value in fields.items():
                self.settings[key] = value.get().strip()
            try:
                self.save_settings()
            except OSError as exc:
                messagebox.showerror(
                    "Save failed",
                    f"Could not save company details:\n{exc}",
                    parent=details_win,
                )
                return
            messagebox.showinfo("Success", "Company details saved.", parent=details_win)
            details_win.destroy()

        btn_frame = tk.Frame(details_win)
        btn_frame.grid(row=len(field_labels), column=0, columnspan=2, pady=20)
        tk.Button(
            btn_frame,
            text="Save",
            command=save_company_details,
            bg="#2196F3",
            fg="white",
        ).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Cancel", command=details_win.destroy).pack(
            side=tk.LEFT, padx=10
        )

    def open_item_window(self, parent_win, item_list, refresh_callback, item_index=None):
        if self.show_changes_blocked(parent_win):
            return

        win = tk.Toplevel(parent_win)
        win.title("Item Details & Operations")
        screen_width = win.winfo_screenwidth()
        screen_height = win.winfo_screenheight()
        window_width = int(screen_width * 0.5)
        window_height = max(300, screen_height - 80)
        window_x = (screen_width - window_width) // 2
        window_y = 0
        win.geometry(f"{window_width}x{window_height}+{window_x}+{window_y}")
        win.grab_set()

        footer_frame = tk.Frame(win)
        footer_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=8)

        is_editing = item_index is not None
        item_data = item_list[item_index] if is_editing else {}
        temp_operations = list(item_data.get("operations", []))

        info_frame = tk.Frame(win)
        info_frame.pack(fill=tk.X, padx=15, pady=10)

        tk.Label(info_frame, text="Item Name (e.g. Top SUB):").grid(row=0, column=0, sticky="e", pady=5)
        ent_item_name = tk.Entry(info_frame, width=40)
        ent_item_name.grid(row=0, column=1, padx=10, pady=5)
        self.capitalize_words_on_focus_out(ent_item_name)

        tk.Label(info_frame, text="Required Date:").grid(row=1, column=0, sticky="e", pady=5)
        stored_item_date = str(item_data.get("req_date", "")).strip() if is_editing else ""
        parsed_item_date = None
        for date_format in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"):
            try:
                parsed_item_date = datetime.strptime(stored_item_date, date_format).date()
                break
            except ValueError:
                continue

        item_date_var = tk.StringVar(
            value=(
                parsed_item_date.strftime("%d.%m.%Y")
                if parsed_item_date
                else stored_item_date
            )
        )
        item_date_options = ["Select...", "Specific date"]
        item_date_options.extend(
            f"{amount} day" if amount == 1 else f"{amount} days"
            for amount in range(1, 6)
        )
        item_date_options.extend(
            f"{amount} week" if amount == 1 else f"{amount} weeks"
            for amount in range(1, 6)
        )
        item_date_choice_var = tk.StringVar(
            value="Specific date" if parsed_item_date else "Select..."
        )
        item_date_frame = tk.Frame(info_frame)
        item_date_frame.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        ent_req_date = tk.Entry(
            item_date_frame,
            textvariable=item_date_var,
            width=14,
            state="readonly",
            justify="center",
        )
        ent_req_date.pack(side=tk.LEFT, padx=4)
        item_date_choice = ttk.Combobox(
            item_date_frame,
            textvariable=item_date_choice_var,
            values=item_date_options,
            state="readonly",
            width=14,
        )
        item_date_choice.pack(side=tk.LEFT, padx=4)

        def set_item_required_date(chosen_date):
            item_date_var.set(chosen_date.strftime("%d.%m.%Y"))
            item_date_choice_var.set("Specific date")

        def open_item_required_date_picker():
            try:
                initial_date = datetime.strptime(item_date_var.get(), "%d.%m.%Y").date()
            except ValueError:
                initial_date = date.today()
            self.open_required_date_calendar(
                win,
                initial_date,
                set_item_required_date,
            )

        def apply_item_required_date_option(event=None):
            option = item_date_choice_var.get()
            if option == "Specific date":
                open_item_required_date_picker()
            elif option != "Select...":
                amount = int(option.split()[0])
                unit = option.split()[1]
                offset = timedelta(days=amount * (7 if unit.startswith("week") else 1))
                set_item_required_date(date.today() + offset)
                item_date_choice_var.set(option)
            else:
                item_date_var.set("")

        item_date_choice.bind(
            "<<ComboboxSelected>>",
            apply_item_required_date_option,
        )
        tk.Button(
            item_date_frame,
            text="Choose date...",
            command=open_item_required_date_picker,
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            item_date_frame,
            text="Clear",
            command=lambda: (
                item_date_var.set(""),
                item_date_choice_var.set("Select..."),
            ),
        ).pack(side=tk.LEFT, padx=4)

        tk.Label(info_frame, text="Drawing Number:").grid(row=2, column=0, sticky="e", pady=5)
        ent_drawing_number = tk.Entry(info_frame, width=40)
        ent_drawing_number.grid(row=2, column=1, padx=10, pady=5, sticky="w")

        tk.Label(info_frame, text="Revision:").grid(row=3, column=0, sticky="e", pady=5)
        ent_revision = tk.Entry(info_frame, width=20)
        ent_revision.grid(row=3, column=1, padx=10, pady=5, sticky="w")

        tk.Label(info_frame, text="Quantity:").grid(row=4, column=0, sticky="e", pady=5)
        ent_quantity = tk.Entry(info_frame, width=10, justify="right")
        ent_quantity.grid(row=4, column=1, padx=10, pady=5, sticky="w")
        ent_quantity.insert(0, str(item_data.get("quantity", 1) if is_editing else 1))
        self.clear_zero_on_click(ent_quantity)

        if is_editing:
            ent_item_name.insert(0, item_data.get("name", ""))
            ent_drawing_number.insert(0, item_data.get("drawing_number", ""))
            ent_revision.insert(0, item_data.get("revision", ""))

        op_frame = tk.LabelFrame(win, text="Machining Processes per Unit")
        op_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        add_op_frame = tk.Frame(op_frame)
        add_op_frame.pack(fill=tk.X, pady=10, padx=5)

        tk.Label(add_op_frame, text="Operation:").pack(side=tk.LEFT, padx=(0, 5))
        non_operation_settings = {
            "VAT_Rate",
            "Starting_Quote_No",
            "Starting_Order_No",
            "Starting_Delivery_Note_No",
            "Logo_Path",
            "Pdf_Output_Directory",
            "Company_Name",
            "Company_Address",
            "Company_Postcode",
            "Company_Reg_No",
            "VAT_Reg_No",
            "Company_Phone_Landline",
            "Company_Phone_Mobile",
            "PDF_Layouts",
        }
        op_types = [key for key in self.settings if key not in non_operation_settings]
        cb_type = ttk.Combobox(add_op_frame, values=op_types, state="readonly", width=15)
        cb_type.pack(side=tk.LEFT, padx=5)
        if op_types:
            cb_type.current(0)

        tk.Label(add_op_frame, text="Time per unit [h]:").pack(side=tk.LEFT, padx=(10, 5))
        ent_time = tk.Entry(add_op_frame, width=10)
        ent_time.pack(side=tk.LEFT, padx=5)
        self.clear_zero_on_click(ent_time)

        columns_op = ("type", "time", "rate", "cost")
        op_tree_frame = tk.Frame(op_frame)
        op_tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        op_tree = GridTreeview(
            op_tree_frame,
            columns=columns_op,
            show="tree headings",
            height=6,
        )
        op_tree.heading("#0", text="Line")
        op_tree.column("#0", width=45, anchor=tk.CENTER, stretch=False)
        op_tree.heading("type", text="Operation Type")
        op_tree.heading("time", text="Time (h)")
        op_tree.heading("rate", text="Rate (/h)")
        op_tree.heading("cost", text="Cost")

        op_tree.column("type", width=150)
        op_tree.column("time", width=100, anchor=tk.CENTER)
        op_tree.column("rate", width=100, anchor=tk.CENTER)
        op_tree.column("cost", width=120, anchor=tk.E)

        op_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        op_scrollbar = ttk.Scrollbar(
            op_tree_frame,
            orient=tk.VERTICAL,
            command=op_tree.yview,
        )
        op_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        op_tree.configure(yscrollcommand=op_scrollbar.set)

        material_frame = tk.LabelFrame(win, text="Required Material for this Item")
        material_frame.pack(fill=tk.X, padx=15, pady=5)

        tk.Label(material_frame, text="Material:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        ent_material = tk.Entry(material_frame, width=40)
        ent_material.grid(row=0, column=1, columnspan=3, sticky="ew", padx=5, pady=5)
        self.capitalize_words_on_focus_out(ent_material)

        tk.Label(material_frame, text="Material Cost per Unit:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        ent_material_cost = tk.Entry(material_frame, width=12, justify="right")
        ent_material_cost.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        self.clear_zero_on_click(ent_material_cost)

        tk.Label(material_frame, text="Supplier:").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        cb_supplier = ttk.Combobox(
            material_frame,
            width=40,
            values=sorted(self.suppliers, key=str.casefold),
        )
        cb_supplier.grid(row=2, column=1, columnspan=3, sticky="ew", padx=5, pady=5)
        self.capitalize_words_on_focus_out(cb_supplier)

        def manage_suppliers():
            supplier_window = self.open_supplier_database()
            win.wait_window(supplier_window)
            cb_supplier["values"] = sorted(self.suppliers, key=str.casefold)

        tk.Button(
            material_frame,
            text="Supplier Database",
            command=manage_suppliers,
        ).grid(row=3, column=1, sticky="w", padx=5, pady=5)

        tk.Label(material_frame, text="MCT Number:").grid(
            row=4, column=0, sticky="e", padx=5, pady=5
        )
        ent_mct_number = tk.Entry(material_frame, width=25)
        ent_mct_number.grid(row=4, column=1, sticky="w", padx=5, pady=5)

        tk.Label(material_frame, text="Cast:").grid(
            row=4, column=2, sticky="e", padx=5, pady=5
        )
        ent_cast = tk.Entry(material_frame, width=25)
        ent_cast.grid(row=4, column=3, sticky="w", padx=5, pady=5)
        material_frame.columnconfigure(1, weight=1)
        material_frame.columnconfigure(2, weight=0)
        material_frame.columnconfigure(3, weight=0)

        if is_editing:
            ent_material.insert(0, item_data.get("material", ""))
            ent_material_cost.insert(0, str(item_data.get("material_cost", 0) or 0))
            cb_supplier.set(item_data.get("supplier", ""))
            ent_mct_number.insert(0, item_data.get("mct_number", ""))
            ent_cast.insert(0, item_data.get("cast", ""))

        def update_material_section_title(event=None):
            item_name = ent_item_name.get().strip()
            title = f"Required Material for: {item_name}" if item_name else "Required Material for this Item"
            material_frame.config(text=title)

        ent_item_name.bind("<KeyRelease>", update_material_section_title)
        update_material_section_title()

        lbl_item_total = tk.Label(
            footer_frame,
            text="Unit Price: 0.00 | Line Total: 0.00",
            font=("Arial", 10, "bold"),
        )
        lbl_item_total.pack(side=tk.LEFT, padx=5)

        def refresh_operations(resize_window=False):
            for row in op_tree.get_children():
                op_tree.delete(row)

            op_tree.configure(height=max(6, len(temp_operations)))
            try:
                material_cost = float(ent_material_cost.get().strip().replace(",", ".") or 0)
            except ValueError:
                material_cost = 0.0
            try:
                quantity = max(1, int(ent_quantity.get().strip()))
            except ValueError:
                quantity = 1
            item_total = material_cost
            for line_number, op in enumerate(temp_operations, start=1):
                item_total += float(op["cost"])
                op_tree.insert(
                    "",
                    tk.END,
                    text=str(line_number),
                    values=(op["type"], f"{op['time']:.2f}", f"{op['rate']:.2f}", f"{op['cost']:.2f}"),
                )

            lbl_item_total.config(
                text=(
                    f"Unit Price: {item_total:.2f} | "
                    f"Line Total ({quantity} x unit price): {item_total * quantity:.2f}"
                )
            )
            if resize_window:
                win.update_idletasks()
                requested_height = win.winfo_reqheight()
                max_height = max(300, screen_height - 80)
                window_height = min(requested_height, max_height)
                window_x = (screen_width - window_width) // 2
                window_y = 0
                win.geometry(
                    f"{window_width}x{window_height}+{window_x}+{window_y}"
                )

        ent_material_cost.bind("<KeyRelease>", lambda event: refresh_operations())
        ent_material_cost.bind("<FocusOut>", lambda event: refresh_operations())
        ent_quantity.bind("<KeyRelease>", lambda event: refresh_operations())
        ent_quantity.bind("<FocusOut>", lambda event: refresh_operations())

        def add_operation():
            if self.show_changes_blocked(win):
                return

            op_type = cb_type.get()
            time_str = ent_time.get().strip().replace(',', '.')
            if not time_str:
                messagebox.showwarning("Error", "Enter operation time!", parent=win)
                return
            try:
                op_time = float(time_str)
            except ValueError:
                messagebox.showwarning("Error", "Time must be a number!", parent=win)
                return

            rate = self.settings.get(op_type, 0.0)
            cost = op_time * rate

            temp_operations.append({"type": op_type, "time": op_time, "rate": rate, "cost": cost})
            refresh_operations(resize_window=True)
            ent_time.delete(0, tk.END)

        def delete_operation():
            if self.show_changes_blocked(win):
                return

            selected = op_tree.focus()
            if not selected:
                return
            idx = op_tree.index(selected)
            del temp_operations[idx]
            refresh_operations(resize_window=True)

        def edit_operation_on_double_click(event):
            if self.show_changes_blocked(win):
                return

            selected = op_tree.focus()
            if not selected:
                return
            idx = op_tree.index(selected)
            op = temp_operations.pop(idx)

            cb_type.set(op["type"])
            ent_time.delete(0, tk.END)
            ent_time.insert(0, str(op["time"]))
            refresh_operations(resize_window=True)

        op_tree.bind("<Double-1>", edit_operation_on_double_click)

        tk.Button(add_op_frame, text="Add Operation", command=add_operation).pack(side=tk.LEFT, padx=20)
        tk.Button(op_frame, text="Delete Selected Operation", command=delete_operation).pack(side=tk.LEFT, pady=5, anchor="w", padx=10)

        refresh_operations(resize_window=True)

        def save_item():
            if self.show_changes_blocked(win):
                return

            i_name = ent_item_name.get().strip()
            if not i_name:
                messagebox.showwarning("Error", "Item Name is required!", parent=win)
                return

            try:
                material_cost = float(ent_material_cost.get().strip().replace(",", ".") or 0)
                if material_cost < 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning(
                    "Error",
                    "Material cost must be a non-negative number.",
                    parent=win,
                )
                return

            quantity_text = ent_quantity.get().strip()
            try:
                quantity = int(quantity_text)
                if quantity < 1:
                    raise ValueError
            except ValueError:
                messagebox.showwarning(
                    "Invalid quantity",
                    "Quantity must be a whole number greater than zero.",
                    parent=win,
                )
                return

            required_date_text = item_date_var.get().strip()
            item_required_date = ""
            if required_date_text:
                for date_format in ("%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d"):
                    try:
                        item_required_date = datetime.strptime(
                            required_date_text,
                            date_format,
                        ).strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        continue
                else:
                    if required_date_text == stored_item_date:
                        item_required_date = stored_item_date
                    else:
                        messagebox.showerror(
                            "Invalid required date",
                            "Choose a valid required date from the calendar.",
                            parent=win,
                        )
                        return

            new_item_data = {
                "name": i_name,
                "req_date": item_required_date,
                "drawing_number": ent_drawing_number.get().strip(),
                "revision": ent_revision.get().strip(),
                "quantity": quantity,
                "material": ent_material.get().strip(),
                "material_cost": material_cost,
                "supplier": cb_supplier.get().strip(),
                "mct_number": ent_mct_number.get().strip(),
                "cast": ent_cast.get().strip(),
                "operations": temp_operations,
            }
            if is_editing and "actual_work_hours" in item_data:
                new_item_data["actual_work_hours"] = item_data["actual_work_hours"]

            supplier_name = new_item_data["supplier"]
            if supplier_name and supplier_name not in self.suppliers:
                updated_suppliers = dict(self.suppliers)
                updated_suppliers[supplier_name] = {"address": "", "contact": ""}
                try:
                    self.store.save_suppliers(updated_suppliers)
                except OSError as exc:
                    messagebox.showerror(
                        "Supplier save failed",
                        f"Could not save supplier to the database:\n{exc}",
                        parent=win,
                    )
                    return
                self.suppliers = updated_suppliers

            if is_editing:
                item_list[item_index] = new_item_data
            else:
                item_list.append(new_item_data)

            refresh_callback()
            win.destroy()

        tk.Button(
            footer_frame,
            text="Save Item to Quote",
            command=save_item,
            width=20,
            bg="#2196F3",
            fg="white",
            font=("Arial", 10, "bold"),
        ).pack(side=tk.RIGHT, padx=5)
        self.bind_enter_to_next(
            ent_item_name,
            item_date_choice,
            ent_drawing_number,
            ent_revision,
            ent_quantity,
            cb_type,
            ent_time,
            ent_material,
            ent_material_cost,
            cb_supplier,
            ent_mct_number,
            ent_cast,
        )

    def open_quote_window(self, quote_data=None):
        if quote_data is None and self.show_quote_creation_blocked():
            return

        window = tk.Toplevel(self.root)
        is_order = bool(quote_data and quote_data.get("status") == "order")
        window.title("Order Details" if is_order else "Quote Details")
        window.geometry("950x800")
        self.maximize_window(window)
        window.grab_set()

        if quote_data is None:
            new_number = self.next_quote_number()
        else:
            new_number = quote_data["number"]

        temp_items = []
        if quote_data:
            if "items" in quote_data:
                temp_items = [dict(i) for i in quote_data["items"]]
            elif "operations" in quote_data:
                temp_items = [{
                    "name": quote_data.get("name", "Main Part"),
                    "req_date": "",
                    "operations": list(quote_data["operations"]),
                }]
            if len(temp_items) == 1:
                temp_items[0].setdefault(
                    "drawing_number",
                    quote_data.get("drawing_number", ""),
                )
                temp_items[0].setdefault("revision", quote_data.get("revision", ""))

        var_discount = tk.StringVar(value=str(quote_data.get("discount", 0.0)) if quote_data else "0")
        var_markup = tk.StringVar(value=str(quote_data.get("markup", 0.0)) if quote_data else "0")
        order_status_var = tk.StringVar(
            value=(
                "Pending"
                if quote_data.get("order_status") == "Generated"
                else quote_data.get("order_status", "Pending")
            ) if is_order else "Pending"
        )

        top_frame = tk.Frame(window)
        top_frame.pack(fill=tk.X, padx=15, pady=5)
        record_type_label = "ORDER NO" if is_order else "QUOTE NO"
        tk.Label(
            top_frame,
            text=f"{record_type_label}: {new_number}",
            font=("Arial", 14, "bold"),
        ).pack(side=tk.LEFT)

        tk.Label(top_frame, text="Quote Description: ").pack(side=tk.LEFT, padx=(20, 5))
        ent_quote_name = tk.Entry(top_frame, width=40)
        ent_quote_name.pack(side=tk.LEFT)
        self.capitalize_words_on_focus_out(ent_quote_name)
        if quote_data:
            ent_quote_name.insert(0, quote_data.get("name", ""))

        stored_required_date = str(quote_data.get("required_date", "")).strip() if quote_data else ""
        parsed_required_date = None
        for date_format in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"):
            try:
                parsed_required_date = datetime.strptime(stored_required_date, date_format).date()
                break
            except ValueError:
                continue

        required_date_var = tk.StringVar(
            value=parsed_required_date.strftime("%d.%m.%Y") if parsed_required_date else ""
        )
        required_date_options = ["Select...", "Specific date"]
        required_date_options.extend(f"{amount} day" if amount == 1 else f"{amount} days" for amount in range(1, 6))
        required_date_options.extend(f"{amount} week" if amount == 1 else f"{amount} weeks" for amount in range(1, 6))
        selected_date_option = quote_data.get("required_date_option", "") if quote_data else ""
        if not selected_date_option and parsed_required_date:
            selected_date_option = "Specific date"
        if selected_date_option not in required_date_options:
            selected_date_option = "Select..."
        required_date_option_var = tk.StringVar(value=selected_date_option)

        required_date_frame = tk.Frame(window)
        required_date_frame.pack(fill=tk.X, padx=15, pady=(0, 5))
        tk.Label(required_date_frame, text="Date Required:").pack(side=tk.LEFT, padx=(0, 8))
        tk.Entry(
            required_date_frame,
            textvariable=required_date_var,
            width=14,
            state="readonly",
            justify="center",
        ).pack(side=tk.LEFT, padx=4)
        required_date_choice = ttk.Combobox(
            required_date_frame,
            textvariable=required_date_option_var,
            values=required_date_options,
            state="readonly",
            width=16,
        )
        required_date_choice.pack(side=tk.LEFT, padx=4)

        def set_required_date(chosen_date):
            required_date_var.set(chosen_date.strftime("%d.%m.%Y"))
            required_date_option_var.set("Specific date")

        def open_required_date_picker():
            try:
                initial_date = datetime.strptime(required_date_var.get(), "%d.%m.%Y").date()
            except ValueError:
                initial_date = date.today()
            self.open_required_date_calendar(window, initial_date, set_required_date)

        def apply_required_date_option(event=None):
            option = required_date_option_var.get()
            if option == "Specific date":
                open_required_date_picker()
            elif option != "Select...":
                amount = int(option.split()[0])
                unit = option.split()[1]
                offset = timedelta(days=amount * (7 if unit.startswith("week") else 1))
                set_required_date(date.today() + offset)
                required_date_option_var.set(option)
            else:
                required_date_var.set("")

        required_date_choice.bind("<<ComboboxSelected>>", apply_required_date_option)
        tk.Button(
            required_date_frame,
            text="Choose date...",
            command=open_required_date_picker,
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            required_date_frame,
            text="Clear",
            command=lambda: (required_date_var.set(""), required_date_option_var.set("Select...")),
        ).pack(side=tk.LEFT, padx=4)

        if is_order:
            order_status_frame = tk.LabelFrame(window, text="Order Status")
            order_status_frame.pack(fill=tk.X, padx=15, pady=5)
            tk.Label(order_status_frame, text="Status:").pack(side=tk.LEFT, padx=(8, 4), pady=6)
            order_status_choice = ttk.Combobox(
                order_status_frame,
                textvariable=order_status_var,
                values=("Pending", "Completed", "Invoiced"),
                state="readonly",
                width=16,
            )
            order_status_choice.pack(side=tk.LEFT, padx=4, pady=6)
            tk.Label(order_status_frame, text="Customer PO Number:").pack(
                side=tk.LEFT,
                padx=(20, 4),
                pady=6,
            )
            customer_po_entry = tk.Entry(order_status_frame, width=28)
            customer_po_entry.pack(side=tk.LEFT, padx=4, pady=6)
            customer_po_entry.insert(
                0,
                quote_data.get("customer_po_number", "") if quote_data else "",
            )

        customer_frame = tk.LabelFrame(window, text="Customer Details")
        customer_frame.pack(fill=tk.X, padx=15, pady=10)

        tk.Label(customer_frame, text="Company Name:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        cb_cust_name = ttk.Combobox(customer_frame, width=32)
        cb_cust_name["values"] = list(self.customers.keys())
        cb_cust_name.grid(row=0, column=1, padx=5, pady=5)
        self.capitalize_words_on_focus_out(cb_cust_name)

        tk.Label(customer_frame, text="Address:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        ent_cust_addr = tk.Text(customer_frame, width=58, height=3, wrap=tk.WORD)
        ent_cust_addr.grid(row=1, column=1, columnspan=3, padx=5, pady=5, sticky="ew")
        self.capitalize_words_on_focus_out(ent_cust_addr)

        tk.Label(customer_frame, text="Contact Person:").grid(row=0, column=2, sticky="e", padx=(20, 5), pady=5)
        cb_cust_contact = ttk.Combobox(customer_frame, width=25)
        cb_cust_contact.grid(row=0, column=3, padx=5, pady=5)
        self.capitalize_words_on_focus_out(cb_cust_contact)

        tk.Label(customer_frame, text="Phone Number:").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        ent_cust_phone = tk.Entry(customer_frame, width=25)
        ent_cust_phone.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        tk.Label(customer_frame, text="Email:").grid(row=2, column=2, sticky="e", padx=5, pady=5)
        ent_cust_email = tk.Entry(customer_frame, width=35)
        ent_cust_email.grid(row=2, column=3, padx=5, pady=5, sticky="w")

        def set_text(widget, value):
            widget.delete("1.0", tk.END)
            widget.insert("1.0", value)

        def set_entry(widget, value):
            widget.delete(0, tk.END)
            widget.insert(0, value)

        def fill_contact_details(event=None):
            company = self.customers.get(cb_cust_name.get().strip(), {})
            contact = company.get("contacts", {}).get(cb_cust_contact.get().strip(), {})
            set_entry(ent_cust_phone, contact.get("phone", ""))
            set_entry(ent_cust_email, contact.get("email", ""))

        def fill_company_details(event=None):
            company = self.customers.get(cb_cust_name.get().strip())
            if not company:
                return
            set_text(ent_cust_addr, company.get("address", ""))
            cb_cust_contact["values"] = list(company.get("contacts", {}).keys())
            cb_cust_contact.set("")
            set_entry(ent_cust_phone, "")
            set_entry(ent_cust_email, "")

        cb_cust_name.bind("<<ComboboxSelected>>", fill_company_details)
        cb_cust_name.bind("<FocusOut>", fill_company_details)
        cb_cust_contact.bind("<<ComboboxSelected>>", fill_contact_details)

        if quote_data:
            cd = quote_data.get("customer", {})
            if isinstance(cd, dict):
                cb_cust_name.set(cd.get("name", ""))
                fill_company_details()
                cb_cust_contact.set(cd.get("contact", ""))
                fill_contact_details()
                if not ent_cust_addr.get("1.0", tk.END).strip():
                    set_text(ent_cust_addr, cd.get("address", ""))
                if not ent_cust_phone.get():
                    set_entry(ent_cust_phone, cd.get("phone", ""))
                if not ent_cust_email.get():
                    set_entry(ent_cust_email, cd.get("email", ""))
            else:
                cb_cust_name.set(str(cd))

        items_frame = tk.LabelFrame(window, text="Items to Quote (Parts)")
        items_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        btn_items_frame = tk.Frame(items_frame)
        btn_items_frame.pack(fill=tk.X, pady=5, padx=5)

        if is_order:
            work_time_frame = tk.LabelFrame(items_frame, text="Actual Work Time by Item")
            work_time_frame.pack(fill=tk.X, padx=5, pady=5)
            tk.Label(work_time_frame, text="Item:").pack(side=tk.LEFT, padx=(8, 4), pady=6)
            work_item_var = tk.StringVar()
            work_item_choice = ttk.Combobox(
                work_time_frame,
                textvariable=work_item_var,
                state="readonly",
                width=28,
            )
            work_item_choice.pack(side=tk.LEFT, padx=4, pady=6)
            tk.Label(work_time_frame, text="Actual batch time (h):").pack(
                side=tk.LEFT, padx=(10, 4), pady=6
            )
            actual_hours_var = tk.StringVar()
            actual_hours_entry = tk.Entry(
                work_time_frame,
                textvariable=actual_hours_var,
                width=10,
                justify=tk.RIGHT,
            )
            actual_hours_entry.pack(side=tk.LEFT, padx=4, pady=6)
            work_time_result = tk.Label(
                work_time_frame,
                text="Select an item",
                font=("Arial", 10, "bold"),
            )
            work_time_result.pack(side=tk.LEFT, padx=8, pady=6)

            def refresh_work_item_choices(selected_index=None):
                work_item_choice["values"] = tuple(
                    f"{index + 1}. {item.get('name', 'Item')}"
                    for index, item in enumerate(temp_items)
                )
                if not temp_items:
                    work_item_var.set("")
                    actual_hours_var.set("")
                    work_time_result.config(text="No items available", fg="#475569")
                    return
                if selected_index is None:
                    selected_index = work_item_choice.current()
                if selected_index < 0 or selected_index >= len(temp_items):
                    selected_index = 0
                work_item_choice.current(selected_index)
                refresh_work_time_details()

            def refresh_work_time_details(event=None):
                selected_index = work_item_choice.current()
                if selected_index < 0 or selected_index >= len(temp_items):
                    actual_hours_var.set("")
                    work_time_result.config(text="Select an item", fg="#475569")
                    return
                item = temp_items[selected_index]
                actual_hours = item.get("actual_work_hours")
                actual_hours_var.set("" if actual_hours is None else str(actual_hours))
                planned_hours = self.get_planned_operation_hours(item)
                if actual_hours is None:
                    text = (
                        f"Planned: {planned_hours:.2f} h — enter actual time"
                        if planned_hours > 0
                        else "No planned operation time"
                    )
                    work_time_result.config(text=text, fg="#475569")
                elif planned_hours <= 0:
                    work_time_result.config(
                        text=f"Actual: {float(actual_hours):.2f} h — no planned time",
                        fg="#475569",
                    )
                elif float(actual_hours) > planned_hours:
                    work_time_result.config(
                        text=f"Too long: {float(actual_hours):.2f} h / {planned_hours:.2f} h",
                        fg="#DC2626",
                    )
                else:
                    work_time_result.config(
                        text=f"On time: {float(actual_hours):.2f} h / {planned_hours:.2f} h",
                        fg="#15803D",
                    )

            def apply_actual_work_time():
                selected_index = work_item_choice.current()
                if selected_index < 0 or selected_index >= len(temp_items):
                    messagebox.showinfo("Information", "Select an item first.", parent=window)
                    return
                value = actual_hours_var.get().strip().replace(",", ".")
                if value:
                    try:
                        actual_hours = float(value)
                        if actual_hours < 0:
                            raise ValueError
                    except ValueError:
                        messagebox.showerror(
                            "Invalid work time",
                            "Enter a non-negative number of hours.",
                            parent=window,
                        )
                        return
                    temp_items[selected_index]["actual_work_hours"] = actual_hours
                else:
                    temp_items[selected_index].pop("actual_work_hours", None)
                refresh_work_time_details()

            work_item_choice.bind("<<ComboboxSelected>>", refresh_work_time_details)
            tk.Button(
                work_time_frame,
                text="Apply to Item",
                command=apply_actual_work_time,
            ).pack(side=tk.LEFT, padx=5, pady=6)
            refresh_work_item_choices(0)

        columns_items = (
            "name",
            "drawing_number",
            "revision",
            "quantity",
            "req_date",
            "material",
            "material_cost",
            "supplier",
            "unit_price",
            "cost",
        )
        items_table_frame = tk.Frame(items_frame)
        items_table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        items_tree = GridTreeview(
            items_table_frame,
            columns=columns_items,
            show="tree headings",
            height=8,
        )
        items_tree.heading("#0", text="Line")
        items_tree.column("#0", width=45, anchor=tk.CENTER, stretch=False)
        items_tree.heading("name", text="Item Name")
        items_tree.heading("drawing_number", text="Drawing Number")
        items_tree.heading("revision", text="Revision")
        items_tree.heading("quantity", text="Qty")
        items_tree.heading("req_date", text="Required Date")
        items_tree.heading("material", text="Required Material")
        items_tree.heading("material_cost", text="Material / Unit")
        items_tree.heading("supplier", text="Supplier")
        items_tree.heading("unit_price", text="Unit Price ex VAT")
        items_tree.heading("cost", text="Line Total ex VAT")

        items_tree.column("name", width=200)
        items_tree.column("drawing_number", width=150)
        items_tree.column("revision", width=80, anchor=tk.CENTER)
        items_tree.column("quantity", width=55, anchor=tk.CENTER)
        items_tree.column("req_date", width=120, anchor=tk.CENTER)
        items_tree.column("material", width=170)
        items_tree.column("material_cost", width=110, anchor=tk.E)
        items_tree.column("supplier", width=150)
        items_tree.column("unit_price", width=110, anchor=tk.E)
        items_tree.column("cost", width=130, anchor=tk.E)
        items_vertical_scrollbar = ttk.Scrollbar(
            items_table_frame,
            orient=tk.VERTICAL,
            command=items_tree.yview,
        )
        items_horizontal_scrollbar = ttk.Scrollbar(
            items_frame,
            orient=tk.HORIZONTAL,
            command=items_tree.xview,
        )
        items_tree.configure(
            yscrollcommand=items_vertical_scrollbar.set,
            xscrollcommand=items_horizontal_scrollbar.set,
        )
        items_vertical_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        items_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        items_horizontal_scrollbar.pack(fill=tk.X, padx=5)

        totals_frame = tk.Frame(items_frame)
        totals_frame.pack(side=tk.RIGHT, padx=10, pady=10)

        tk.Label(totals_frame, text="Markup (%):").grid(row=0, column=0, sticky="e", pady=2)
        ent_markup = tk.Entry(
            totals_frame,
            width=8,
            textvariable=var_markup,
            justify="right",
            state="readonly" if is_order else "normal",
        )
        ent_markup.grid(row=0, column=1, sticky="e", pady=2)

        tk.Label(totals_frame, text="Discount (%):").grid(row=1, column=0, sticky="e", pady=2)
        ent_discount = tk.Entry(
            totals_frame,
            width=8,
            textvariable=var_discount,
            justify="right",
            state="readonly" if is_order else "normal",
        )
        ent_discount.grid(row=1, column=1, sticky="e", pady=2)
        if not is_order:
            self.clear_zero_on_click(ent_markup)
            self.clear_zero_on_click(ent_discount)

        lbl_subtotal = tk.Label(totals_frame, text="Subtotal: 0.00")
        lbl_markup_amount = tk.Label(totals_frame, text="Markup Amount: 0.00")
        lbl_markup_amount.grid(row=2, column=0, columnspan=2, sticky="e", pady=2)
        lbl_subtotal.grid(row=3, column=0, columnspan=2, sticky="e", pady=2)

        lbl_net = tk.Label(totals_frame, text="Net Total: 0.00")
        lbl_net.grid(row=4, column=0, columnspan=2, sticky="e", pady=2)

        lbl_vat = tk.Label(totals_frame, text="VAT Amount: 0.00")
        lbl_vat.grid(row=5, column=0, columnspan=2, sticky="e", pady=2)

        lbl_gross = tk.Label(totals_frame, text="Gross Total: 0.00", font=("Arial", 11, "bold"))
        lbl_gross.grid(row=6, column=0, columnspan=2, sticky="e", pady=5)

        def refresh_items_and_totals(*args):
            selected_work_item = (
                work_item_choice.current()
                if is_order
                else None
            )
            for row in items_tree.get_children():
                items_tree.delete(row)

            for idx, item in enumerate(temp_items):
                unit_cost = float(item.get("material_cost", 0) or 0) + sum(
                    float(op["cost"]) for op in item.get("operations", [])
                )
                quantity = int(item.get("quantity", 1) or 1)
                try:
                    markup_val = float(var_markup.get().replace(",", ".") or 0)
                except ValueError:
                    markup_val = 0.0
                unit_price = unit_cost * (1 + markup_val / 100.0)
                line_total = unit_price * quantity
                items_tree.insert(
                    "",
                    tk.END,
                    iid=str(idx),
                    text=str(idx + 1),
                    values=(
                        item.get("name", ""),
                        item.get("drawing_number", ""),
                        item.get("revision", ""),
                        quantity,
                        item.get("req_date", ""),
                        item.get("material", ""),
                        f"{float(item.get('material_cost', 0) or 0):.2f}",
                        item.get("supplier", ""),
                        f"{unit_price:.2f}",
                        f"{line_total:.2f}",
                    ),
                )

            try:
                discount_val = float(var_discount.get().replace(',', '.') or 0)
            except ValueError:
                discount_val = 0.0
            try:
                markup_val = float(var_markup.get().replace(",", ".") or 0)
            except ValueError:
                markup_val = 0.0

            subtotal, discount_amt, net_total, vat_amt, gross_total = self.calculate_quote_totals(
                temp_items,
                discount_val,
                markup_val,
            )
            cost_subtotal = sum(
                (
                    float(item.get("material_cost", 0) or 0)
                    + sum(float(operation.get("cost", 0) or 0) for operation in item.get("operations", []))
                ) * int(item.get("quantity", 1) or 1)
                for item in temp_items
            )
            vat_rate = self.settings.get("VAT_Rate", 20.0)

            lbl_markup_amount.config(text=f"Markup Amount: {subtotal - cost_subtotal:.2f}")
            lbl_subtotal.config(text=f"Subtotal: {subtotal:.2f}")
            lbl_net.config(text=f"Net Total: {net_total:.2f}")
            lbl_vat.config(text=f"VAT ({vat_rate}%): {vat_amt:.2f}")
            lbl_gross.config(text=f"Gross Total: {gross_total:.2f}")
            if is_order:
                refresh_work_item_choices(selected_work_item)

        var_discount.trace_add("write", refresh_items_and_totals)
        var_markup.trace_add("write", refresh_items_and_totals)

        def add_item_cmd():
            if self.show_changes_blocked(window):
                return
            if is_order:
                return
            self.open_item_window(window, temp_items, refresh_items_and_totals)

        def edit_item_cmd(event=None):
            if self.show_changes_blocked(window):
                return
            if is_order:
                return
            selected = items_tree.focus()
            if not selected:
                return
            idx = int(selected)
            self.open_item_window(window, temp_items, refresh_items_and_totals, item_index=idx)

        def delete_item_cmd():
            if self.show_changes_blocked(window):
                return
            if is_order:
                return
            selected = items_tree.focus()
            if not selected:
                return
            idx = int(selected)
            del temp_items[idx]
            refresh_items_and_totals()

        def view_item_cmd(event=None):
            selected = items_tree.focus()
            if not selected:
                return
            idx = int(selected)
            if idx < 0 or idx >= len(temp_items):
                return

            item = temp_items[idx]
            details_window = tk.Toplevel(window)
            details_window.title(f"Order Item Details - {item.get('name', 'Item')}")
            details_window.geometry("720x520")
            self.maximize_window(details_window)
            details_window.transient(window)

            details_frame = tk.LabelFrame(details_window, text="Item Details")
            details_frame.pack(fill=tk.X, padx=12, pady=10)
            details_frame.columnconfigure(1, weight=1)
            for row, (label, value) in enumerate((
                ("Item Name:", item.get("name", "")),
                ("Drawing Number:", item.get("drawing_number", "")),
                ("Revision:", item.get("revision", "")),
                ("Quantity:", str(item.get("quantity", 1) or 1)),
                ("Required Date:", item.get("req_date", "")),
                ("Required Material:", item.get("material", "")),
                ("Material Cost per Unit:", f"{float(item.get('material_cost', 0) or 0):.2f}"),
                ("Supplier:", item.get("supplier", "")),
                ("MCT Number:", item.get("mct_number", "")),
                ("Cast:", item.get("cast", "")),
            )):
                tk.Label(details_frame, text=label).grid(
                    row=row,
                    column=0,
                    sticky="e",
                    padx=6,
                    pady=4,
                )
                tk.Label(
                    details_frame,
                    text=value or "-",
                    anchor=tk.W,
                    justify=tk.LEFT,
                ).grid(row=row, column=1, sticky="ew", padx=6, pady=4)

            planned_hours = self.get_planned_operation_hours(item)
            actual_hours = item.get("actual_work_hours")
            if actual_hours is None:
                work_time_text = f"Actual work time: Not recorded | Planned: {planned_hours:.2f} h"
                work_time_color = "#475569"
            elif planned_hours <= 0:
                work_time_text = (
                    f"Actual work time: {float(actual_hours):.2f} h | "
                    "No planned operation time"
                )
                work_time_color = "#475569"
            elif float(actual_hours) > planned_hours:
                work_time_text = (
                    f"Too long: {float(actual_hours):.2f} h / "
                    f"{planned_hours:.2f} h planned"
                )
                work_time_color = "#DC2626"
            else:
                work_time_text = (
                    f"On time: {float(actual_hours):.2f} h / "
                    f"{planned_hours:.2f} h planned"
                )
                work_time_color = "#15803D"
            tk.Label(
                details_window,
                text=work_time_text,
                font=("Arial", 11, "bold"),
                fg=work_time_color,
            ).pack(anchor=tk.W, padx=16, pady=(4, 8))

            operation_frame = tk.LabelFrame(details_window, text="Planned Operations")
            operation_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=5)
            operation_tree = GridTreeview(
                operation_frame,
                columns=("type", "time", "rate", "cost"),
                show="tree headings",
            )
            operation_tree.heading("#0", text="Line")
            operation_tree.column("#0", width=50, anchor=tk.CENTER, stretch=False)
            for column, heading in (
                ("type", "Operation"),
                ("time", "Time / Unit (h)"),
                ("rate", "Rate (/h)"),
                ("cost", "Cost / Unit"),
            ):
                operation_tree.heading(column, text=heading)
            operation_tree.column("type", width=200)
            operation_tree.column("time", width=150, anchor=tk.CENTER)
            operation_tree.column("rate", width=120, anchor=tk.E)
            operation_tree.column("cost", width=120, anchor=tk.E)
            operation_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
            for line_number, operation in enumerate(item.get("operations", []), start=1):
                operation_tree.insert(
                    "",
                    tk.END,
                    text=str(line_number),
                    values=(
                        operation.get("type", ""),
                        f"{float(operation.get('time', 0) or 0):.2f}",
                        f"{float(operation.get('rate', 0) or 0):.2f}",
                        f"{float(operation.get('cost', 0) or 0):.2f}",
                    ),
                )

            tk.Button(
                details_window,
                text="Close",
                command=details_window.destroy,
                width=12,
            ).pack(side=tk.RIGHT, padx=12, pady=10)

        item_action_state = tk.DISABLED if is_order else tk.NORMAL
        if is_order:
            tk.Button(
                btn_items_frame,
                text="View Selected Item",
                command=view_item_cmd,
            ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_items_frame,
            text="Add New Item",
            command=add_item_cmd,
            state=item_action_state,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_items_frame,
            text="Edit Selected Item",
            command=edit_item_cmd,
            state=item_action_state,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_items_frame,
            text="Copy Item",
            command=lambda: self.copy_selected_item(items_tree, temp_items, window),
            state=item_action_state,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_items_frame,
            text="Paste Item",
            command=lambda: self.paste_item(temp_items, refresh_items_and_totals, window),
            state=item_action_state,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_items_frame,
            text="Delete Item",
            command=delete_item_cmd,
            state=item_action_state,
        ).pack(side=tk.LEFT, padx=5)

        items_tree.bind(
            "<Double-1>",
            view_item_cmd if is_order else edit_item_cmd,
        )
        quote_inputs = [
            ent_quote_name,
            required_date_choice,
            cb_cust_name,
            ent_cust_addr,
            cb_cust_contact,
            ent_cust_phone,
            ent_cust_email,
        ]
        if is_order:
            quote_inputs.extend(
                (
                    order_status_choice,
                    customer_po_entry,
                    work_item_choice,
                    actual_hours_entry,
                )
            )
        quote_inputs.extend((ent_markup, ent_discount))
        self.bind_enter_to_next(*quote_inputs)
        refresh_items_and_totals()

        def save(close_window=True):
            if self.show_changes_blocked(window):
                return False

            q_name = ent_quote_name.get().strip()
            cust_name = cb_cust_name.get().strip()

            if not cust_name or not q_name:
                messagebox.showwarning("Error", "'Company Name' and 'Quote Description' fields are required!", parent=window)
                return False

            try:
                discount_val = float(var_discount.get().replace(',', '.') or 0)
            except ValueError:
                messagebox.showwarning("Error", "Discount must be a valid number!", parent=window)
                return False
            try:
                markup_val = float(var_markup.get().replace(",", ".") or 0)
                if not math.isfinite(markup_val) or markup_val < 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning(
                    "Error",
                    "Markup must be a non-negative number.",
                    parent=window,
                )
                return False

            required_date_text = required_date_var.get().strip()
            required_date_iso = ""
            if required_date_text:
                try:
                    required_date_iso = datetime.strptime(
                        required_date_text,
                        "%d.%m.%Y",
                    ).date().isoformat()
                except ValueError:
                    messagebox.showwarning(
                        "Error",
                        "Select a valid required date.",
                        parent=window,
                    )
                    return False

            cust_address = ent_cust_addr.get("1.0", tk.END).strip()
            cust_contact = cb_cust_contact.get().strip()
            cust_phone = ent_cust_phone.get().strip()
            cust_email = ent_cust_email.get().strip()

            company_data = self.customers.setdefault(
                cust_name,
                {"address": "", "contacts": {}},
            )
            company_data["address"] = cust_address
            company_data.setdefault("contacts", {})
            if cust_contact:
                company_data["contacts"][cust_contact] = {
                    "phone": cust_phone,
                    "email": cust_email,
                }
            self.customers[cust_name] = company_data

            self.save_customers()
            cb_cust_name["values"] = list(self.customers.keys())
            cb_cust_contact["values"] = list(company_data["contacts"].keys())

            customer_snapshot = {
                "name": cust_name,
                "address": cust_address,
                "contact": cust_contact,
                "phone": cust_phone,
                "email": cust_email,
            }

            new_data = {
                "number": new_number,
                "name": q_name,
                "markup": markup_val,
                "discount": discount_val,
                "required_date": required_date_iso,
                "required_date_option": (
                    required_date_option_var.get()
                    if required_date_iso
                    else ""
                ),
                "customer": customer_snapshot,
                "items": temp_items,
            }

            if quote_data is None:
                new_data["status"] = "quote"
                self.quotes.append(new_data)
            else:
                if is_order:
                    selected_status = order_status_var.get()
                    if selected_status not in ("Pending", "Completed", "Invoiced"):
                        messagebox.showerror(
                            "Invalid status",
                            "Choose Pending, Completed, or Invoiced.",
                            parent=window,
                        )
                        return False
                    new_data["order_status"] = selected_status
                    new_data["job_card_generated"] = (
                        quote_data.get("job_card_generated", False)
                        or quote_data.get("order_status") == "Generated"
                    )
                    new_data["customer_po_number"] = customer_po_entry.get().strip()
                quote_data.update(new_data)
                quote_data.pop("drawing_number", None)
                quote_data.pop("revision", None)
                if "operations" in quote_data:
                    del quote_data["operations"]

            self.save_data()
            self.refresh_list()
            if close_window:
                window.destroy()
            return True

        bottom_frame = tk.Frame(window)
        bottom_frame.pack(fill=tk.X, padx=15, pady=10)
        save_label = "Save Order" if is_order else "Save Quote"
        tk.Button(
            bottom_frame,
            text=save_label,
            command=save,
            width=20,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 11, "bold"),
        ).pack(side=tk.RIGHT, padx=5)

        if quote_data is not None and not is_order:
            tk.Button(
                bottom_frame,
                text="Generate PDF",
                command=lambda: self.save_and_generate_quote_pdf(save, quote_data, window),
                width=16,
                bg="#F59E0B",
                fg="white",
            ).pack(side=tk.LEFT, padx=5)
            tk.Button(
                bottom_frame,
                text="Email PDF",
                command=lambda: self.save_and_email_quote(save, quote_data, window),
                width=14,
            ).pack(side=tk.LEFT, padx=5)
        elif is_order:
            tk.Button(
                bottom_frame,
                text="Generate Delivery Note",
                command=lambda: self.save_and_generate_delivery_note(
                    save,
                    quote_data,
                    window,
                ),
                width=22,
                bg="#2563EB",
                fg="white",
            ).pack(side=tk.LEFT, padx=5)

    def save_and_generate_quote_pdf(self, save_callback, quote_data, parent):
        if self.software_is_expired():
            self.generate_pdf(quote_data, parent)
            return
        if save_callback(close_window=False):
            self.generate_pdf(quote_data, parent)

    def save_and_generate_delivery_note(self, save_callback, order, parent):
        if save_callback(close_window=False):
            self.generate_delivery_note(order, parent)

    def save_and_email_quote(self, save_callback, quote_data, parent):
        if self.software_is_expired():
            self.email_quote(quote_data, parent)
            return
        if save_callback(close_window=False):
            self.email_quote(quote_data, parent)

    def add_quote(self):
        self.show_quotes()
        self.open_quote_window()

    def show_quote_creation_blocked(self, parent=None):
        return self.show_changes_blocked(parent)

    def software_is_expired(self):
        end_date_text = str(self.settings.get("Software_End_Date", "")).strip()
        if not end_date_text:
            return False
        try:
            end_datetime = _parse_software_end_datetime(end_date_text)
        except ValueError:
            return True
        return datetime.now() > end_datetime

    def show_changes_blocked(self, parent=None):
        end_date_text = str(self.settings.get("Software_End_Date", "")).strip()
        if not end_date_text:
            return False
        try:
            end_datetime = _parse_software_end_datetime(end_date_text)
        except ValueError:
            messagebox.showerror(
                "Application is read-only",
                "Software End Date or time is invalid. Ask an administrator to correct it in Settings > Admin.",
                parent=parent or self.root,
            )
            return True
        if datetime.now() <= end_datetime:
            return False
        messagebox.showerror(
            "Application is read-only",
            f"Changes are disabled after {end_datetime.strftime('%d.%m.%Y %H:%M')}. "
            "Ask an administrator to change the Software End Date in Settings > Admin.",
            parent=parent or self.root,
        )
        return True

    def next_quote_number(self):
        starting_number = int(self.settings.get("Starting_Quote_No", 1))
        quote_numbers = [
            int(quote["number"])
            for quote in self.quotes
            if quote.get("status", "quote") != "order"
        ]
        if not quote_numbers:
            return starting_number
        highest_number = max(quote_numbers)
        return max(starting_number, highest_number + 1)

    def next_order_number(self):
        starting_number = int(self.settings.get("Starting_Order_No", 1))
        order_numbers = [
            int(order["number"])
            for order in self.quotes
            if order.get("status") == "order"
        ]
        if not order_numbers:
            return starting_number
        return max(starting_number, max(order_numbers) + 1)

    def next_delivery_note_number(self):
        starting_number = int(self.settings.get("Starting_Delivery_Note_No", 1))
        existing_numbers = []
        for order in self.quotes:
            if order.get("status") == "order":
                note_number = order.get("delivery_note_number")
                if note_number is not None:
                    try:
                        existing_numbers.append(int(note_number))
                    except (TypeError, ValueError):
                        continue
        if not existing_numbers:
            return starting_number
        return max(starting_number, max(existing_numbers) + 1)

    def copy_selected_quote(self):
        if self.show_changes_blocked():
            return
        quote = self.get_selected_quote()
        if not quote:
            messagebox.showinfo("Information", "Select a quote to copy.")
            return
        if quote.get("status") == "order":
            messagebox.showinfo("Information", "Only quotes can be copied from the Quotes list.")
            return
        self.quote_clipboard = deepcopy(quote)
        messagebox.showinfo("Copied", f"Quote {quote['number']} is ready to paste.")

    def paste_quote(self):
        if self.show_quote_creation_blocked():
            return
        if self.quote_clipboard is None:
            messagebox.showinfo("Information", "Copy a quote before pasting.")
            return

        pasted_quote = deepcopy(self.quote_clipboard)
        pasted_quote["number"] = self.next_quote_number()
        pasted_quote["status"] = "quote"
        pasted_quote.pop("order_status", None)
        pasted_quote.pop("job_card_generated", None)
        pasted_quote.pop("job_card_generated_date", None)
        pasted_quote.pop("actual_work_hours", None)
        for item in pasted_quote.get("items", []):
            item.pop("actual_work_hours", None)
        try:
            self.quotes.append(pasted_quote)
            self.save_data()
        except OSError as exc:
            if pasted_quote in self.quotes:
                self.quotes.remove(pasted_quote)
            messagebox.showerror("Save failed", f"Could not paste the quote:\n{exc}")
            return
        self.current_view = "quotes"
        self.refresh_list()
        messagebox.showinfo(
            "Pasted",
            f"Quote copied as new quote {pasted_quote['number']}.",
        )

    def copy_selected_item(self, items_tree, items, parent):
        if self.show_changes_blocked(parent):
            return
        selected = items_tree.focus()
        if not selected:
            messagebox.showinfo("Information", "Select an item to copy.", parent=parent)
            return
        index = int(selected)
        if index < 0 or index >= len(items):
            return
        self.item_clipboard = deepcopy(items[index])
        self.item_clipboard.pop("actual_work_hours", None)
        messagebox.showinfo("Copied", "Item is ready to paste.", parent=parent)

    def paste_item(self, items, refresh_callback, parent):
        if self.show_changes_blocked(parent):
            return
        if self.item_clipboard is None:
            messagebox.showinfo("Information", "Copy an item before pasting.", parent=parent)
            return
        pasted_item = deepcopy(self.item_clipboard)
        pasted_item.pop("actual_work_hours", None)
        items.append(pasted_item)
        refresh_callback()

    def edit_quote(self):
        quote_data = self.get_selected_quote()
        if not quote_data:
            messagebox.showinfo("Information", "Select a quote from the list to edit.")
            return

        self.open_quote_window(quote_data)

    def delete_quote(self):
        if self.show_changes_blocked():
            return
        selected = self.tree.focus()
        if not selected:
            messagebox.showinfo("Information", "Select a quote from the list to delete.")
            return

        if messagebox.askyesno("Confirmation", "Are you sure you want to delete this quote?"):
            quote_data = self.get_selected_quote()
            if not quote_data:
                return
            self.quotes = [q for q in self.quotes if q is not quote_data]
            self.save_data()
            self.refresh_list()

    def generate_pdf(self, quote_data=None, parent=None):
        if quote_data is None:
            quote_data = self.get_selected_quote()
        if not quote_data:
            messagebox.showinfo(
                "Information",
                "Select a quote or order from the list to generate PDF.",
                parent=parent,
            )
            return

        try:
            filename = PdfService.generate_pdf(quote_data, self.settings)
            messagebox.showinfo(
                "Success",
                f"PDF generated successfully as:\n{filename}",
                parent=parent,
            )
            try:
                os.startfile(filename)
            except Exception:
                pass
        except RuntimeError as exc:
            messagebox.showerror("Error", str(exc), parent=parent)
        except OSError as exc:
            messagebox.showerror("PDF error", f"Could not save the PDF:\n{exc}", parent=parent)

    def generate_delivery_note(self, order=None, parent=None):
        if order is None:
            order = self.get_selected_quote()
        if not order or order.get("status") != "order":
            messagebox.showinfo(
                "Information",
                "Select an order to generate a delivery note.",
                parent=parent,
            )
            return

        if self.show_changes_blocked(parent):
            return

        if not order.get("delivery_note_number"):
            order["delivery_note_number"] = self.next_delivery_note_number()
            self.save_data()

        try:
            filename = PdfService.generate_delivery_note(order, self.settings)
        except (RuntimeError, OSError) as exc:
            messagebox.showerror("Delivery Note Error", str(exc), parent=parent)
            return

        messagebox.showinfo(
            "Success",
            f"Delivery note generated successfully as:\n{filename}",
            parent=parent,
        )
        try:
            os.startfile(filename)
        except OSError as exc:
            messagebox.showerror(
                "Open PDF Error",
                f"The delivery note was saved, but could not be opened:\n{exc}",
                parent=parent,
            )

    def generate_job_card(self, order=None, parent=None):
        if order is None:
            order = self.get_selected_quote()
        if not order or order.get("status") != "order":
            messagebox.showinfo(
                "Information",
                "Select an order to generate a job card.",
                parent=parent,
            )
            return

        if self.show_changes_blocked(parent):
            return

        try:
            filename = PdfService.generate_job_card(order, self.settings)
        except (RuntimeError, OSError) as exc:
            messagebox.showerror("Job Card Error", str(exc), parent=parent)
            return

        previous_job_card_generated = order.get("job_card_generated")
        previous_job_card_generated_date = order.get("job_card_generated_date")
        order["job_card_generated"] = True
        order["job_card_generated_date"] = datetime.now().strftime("%d.%m.%Y")
        try:
            self.save_data()
        except OSError as exc:
            if previous_job_card_generated is None:
                order.pop("job_card_generated", None)
            else:
                order["job_card_generated"] = previous_job_card_generated
            if previous_job_card_generated_date is None:
                order.pop("job_card_generated_date", None)
            else:
                order["job_card_generated_date"] = previous_job_card_generated_date
            messagebox.showerror(
                "Job Card Status Error",
                f"The job card was saved, but its generated status could not be saved:\n{exc}",
                parent=parent,
            )
            return
        self.refresh_list()

        messagebox.showinfo(
            "Success",
            f"Job card generated successfully as:\n{filename}",
            parent=parent,
        )
        try:
            os.startfile(filename)
        except OSError as exc:
            messagebox.showerror(
                "Open PDF Error",
                f"The job card was saved, but could not be opened:\n{exc}",
                parent=parent,
            )

    def get_selected_quote(self):
        selected = self.tree.focus()
        if not selected:
            return None

        if not selected.startswith("record_"):
            return None
        selected_id = selected[len("record_"):]
        return next(
            (quote for quote in self.quotes if str(id(quote)) == selected_id),
            None,
        )

    def convert_to_order(self):
        if self.show_changes_blocked():
            return
        quote_data = self.get_selected_quote()
        if not quote_data:
            messagebox.showinfo("Information", "Select a quote to change it to an order.")
            return

        if not messagebox.askyesno(
            "Confirmation",
            f"Change quote {quote_data['number']} to an order?",
        ):
            return

        order_number = self.next_order_number()
        quote_data["status"] = "order"
        quote_data["number"] = order_number
        quote_data["order_status"] = "Pending"
        self.save_data()
        self.refresh_list()

    def convert_to_quote(self):
        if self.show_changes_blocked():
            return
        order = self.get_selected_quote()
        if not order or order.get("status") != "order":
            messagebox.showinfo("Information", "Select an order to change it to a quote.")
            return

        if not messagebox.askyesno(
            "Confirmation",
            f"Create a new quote from order {order['number']}? The original order will remain unchanged.",
        ):
            return

        quote = deepcopy(order)
        quote["number"] = self.next_quote_number()
        quote["status"] = "quote"
        quote.pop("order_status", None)
        quote.pop("customer_po_number", None)
        quote.pop("job_card_generated", None)
        quote.pop("job_card_generated_date", None)
        quote.pop("actual_work_hours", None)
        if len(quote.get("items", [])) == 1:
            quote["items"][0].setdefault(
                "drawing_number",
                quote.get("drawing_number", ""),
            )
            quote["items"][0].setdefault("revision", quote.get("revision", ""))
        quote.pop("drawing_number", None)
        quote.pop("revision", None)
        for item in quote.get("items", []):
            item.pop("actual_work_hours", None)

        try:
            self.quotes.append(quote)
            self.save_data()
        except OSError as exc:
            if quote in self.quotes:
                self.quotes.remove(quote)
            messagebox.showerror(
                "Save failed",
                f"Could not create a quote from the order:\n{exc}",
            )
            return

        self.current_view = "quotes"
        self.refresh_list()

    @staticmethod
    def get_planned_operation_hours(item):
        unit_hours = sum(
            float(operation.get("time", 0) or 0)
            for operation in item.get("operations", [])
        )
        return unit_hours * int(item.get("quantity", 1) or 1)

    def open_order_stats(self, parent=None):
        orders = [quote for quote in self.quotes if quote.get("status") == "order"]
        if not orders:
            messagebox.showinfo(
                "Order Stats",
                "There are no orders to include in the financial report.",
                parent=parent or self.root,
            )
            return

        report = tk.Toplevel(parent or self.root)
        report.title("Order Financial Report")
        report.geometry("1250x700")
        self.maximize_window(report)
        report.transient(parent or self.root)

        totals = {"subtotal": 0.0, "discount": 0.0, "net": 0.0, "vat": 0.0, "gross": 0.0}
        status_counts = {
            "Pending": 0,
            "Completed": 0,
            "Invoiced": 0,
        }
        report_rows = []
        for quote in sorted(orders, key=lambda item: int(item.get("number", 0))):
            items = quote.get("items", [])
            if not items and "operations" in quote:
                items = [{"operations": quote["operations"]}]
            discount_pct = float(quote.get("discount", 0.0))
            markup_pct = float(quote.get("markup", 0.0) or 0.0)
            subtotal, discount, net, vat, gross = self.calculate_quote_totals(
                items,
                discount_pct,
                markup_pct,
            )
            status = (
                "Pending"
                if quote.get("order_status") == "Generated"
                else quote.get("order_status", "Pending")
            )
            status_counts[status] = status_counts.get(status, 0) + 1
            totals["subtotal"] += subtotal
            totals["discount"] += discount
            totals["net"] += net
            totals["vat"] += vat
            totals["gross"] += gross

            customer = quote.get("customer", "")
            customer_name = customer.get("name", "") if isinstance(customer, dict) else customer
            report_rows.append(
                (
                    quote.get("number", ""),
                    customer_name,
                    quote.get("name", ""),
                    status,
                    subtotal,
                    discount,
                    net,
                    vat,
                    gross,
                )
            )

        summary = tk.LabelFrame(report, text="Financial Summary - All Orders")
        summary.pack(fill=tk.X, padx=10, pady=(10, 5))
        summary_text = (
            f"Orders: {len(orders)}    "
            f"Pending: {status_counts.get('Pending', 0)}    "
            f"Completed: {status_counts.get('Completed', 0)}    "
            f"Invoiced: {status_counts.get('Invoiced', 0)}"
        )
        tk.Label(summary, text=summary_text, font=("Arial", 10, "bold")).pack(anchor=tk.W, padx=8, pady=5)

        totals_text = (
            f"Subtotal: {totals['subtotal']:.2f}    "
            f"Discount: {totals['discount']:.2f}    "
            f"Net: {totals['net']:.2f}    "
            f"VAT: {totals['vat']:.2f}    "
            f"Gross: {totals['gross']:.2f}"
        )
        tk.Label(summary, text=totals_text, font=("Arial", 11, "bold")).pack(anchor=tk.W, padx=8, pady=(0, 6))

        table_frame = tk.Frame(report)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        columns = ("number", "customer", "description", "status", "subtotal", "discount", "net", "vat", "gross")
        table = GridTreeview(table_frame, columns=columns, show="tree headings")
        table.heading("#0", text="Line")
        table.column("#0", width=50, anchor=tk.CENTER, stretch=False)
        headings = {
            "number": "Order No.",
            "customer": "Customer",
            "description": "Description",
            "status": "Status",
            "subtotal": "Subtotal",
            "discount": "Discount",
            "net": "Net",
            "vat": "VAT",
            "gross": "Gross",
        }
        for column, heading in headings.items():
            table.heading(column, text=heading)
        table.column("number", width=75, anchor=tk.CENTER)
        table.column("customer", width=170)
        table.column("description", width=190)
        table.column("status", width=90, anchor=tk.CENTER)
        for column in ("subtotal", "discount", "net", "vat", "gross"):
            table.column(column, width=95, anchor=tk.E)

        scrollbar_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=table.yview)
        scrollbar_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=table.xview)
        table.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        table.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        for line_number, values in enumerate(report_rows, start=1):
            number, customer, description, status, subtotal, discount, net, vat, gross = values
            table.insert(
                "",
                tk.END,
                text=str(line_number),
                values=(
                    number,
                    customer,
                    description,
                    status,
                    f"{subtotal:.2f}",
                    f"{discount:.2f}",
                    f"{net:.2f}",
                    f"{vat:.2f}",
                    f"{gross:.2f}",
                ),
            )

        def close_report():
            report.destroy()
            if parent is not None and parent.winfo_exists():
                parent.grab_set()

        report.protocol("WM_DELETE_WINDOW", close_report)
        tk.Button(report, text="Close", command=close_report, width=12).pack(pady=(2, 10))
        if parent is not None:
            report.grab_set()
        return report

    def _find_customer_contact(self, customer):
        if not isinstance(customer, dict):
            return None, None

        company_name = customer.get("name", "").strip()
        company = self.customers.get(company_name)
        if not isinstance(company, dict):
            return None, None

        contacts = company.get("contacts", {})
        if not isinstance(contacts, dict) or not contacts:
            return company, None

        contact_name = customer.get("contact", "").strip()
        matching_name = next(
            (name for name in contacts if name.casefold() == contact_name.casefold()),
            None,
        )
        if matching_name is None and len(contacts) == 1:
            matching_name = next(iter(contacts))
        return company, matching_name

    def email_quote(self, quote_data=None, parent=None):
        if quote_data is None:
            quote_data = self.get_selected_quote()
        if not quote_data:
            messagebox.showinfo(
                "Information",
                "Select a quote or order to prepare an email.",
                parent=parent,
            )
            return

        customer = quote_data.get("customer", {})
        email = customer.get("email", "") if isinstance(customer, dict) else ""
        company, contact_name = self._find_customer_contact(customer)
        if not email and company is not None and contact_name is not None:
            contact = company["contacts"].get(contact_name, {})
            email = contact.get("email", "")

        email = email.strip()
        if email and ("@" not in email or any(char.isspace() for char in email)):
            messagebox.showerror(
                "Error",
                "Enter a valid customer email address.",
                parent=parent,
            )
            return

        try:
            filename = os.path.abspath(PdfService.generate_pdf(quote_data, self.settings))
            email_opened_with_attachment = EmailService.open_compose_window(
                email,
                f"Quote {quote_data['number']} - {quote_data.get('name', '')}",
                "Please find the quote attached.",
                filename,
            )
            if email_opened_with_attachment is False:
                messagebox.showinfo(
                    "Attach PDF manually",
                    "The default email application was opened. It does not support "
                    "automatic PDF attachments through Windows MAPI, so attach this file "
                    f"manually:\n{filename}",
                    parent=parent,
                )
            elif email_opened_with_attachment is None:
                return
        except (RuntimeError, OSError) as exc:
            messagebox.showerror("Error", str(exc), parent=parent)


if __name__ == "__main__":
    root = tk.Tk()
    app = CncQuotesApp(root)
    root.mainloop()
