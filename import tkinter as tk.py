import tkinter as tk
from tkinter import ttk, messagebox
import json
import os

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None

DATA_FILE = "quotes_data.json"
SETTINGS_FILE = "cnc_settings.json"
CUSTOMERS_FILE = "customers_data.json"

class CncQuotesApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DM CNC Machining - Quoting System")
        self.root.geometry("900x550")
        
        self.settings = self.load_settings()
        self.customers = self.load_customers()
        self.quotes = self.load_data()
        
        self.create_widgets()
        self.refresh_list()

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save_data(self):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.quotes, f, indent=4, ensure_ascii=False)

    def load_settings(self):
        default_rates = {
            "Turning": 50.0, 
            "Milling": 55.0, 
            "Phosphate": 30.0, 
            "Blasting": 25.0, 
            "VAT_Rate": 20.0,
            "Starting_Quote_No": 1
        }
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    saved_rates = json.load(f)
                    default_rates.update(saved_rates)
            except Exception:
                pass
        return default_rates

    def save_settings(self):
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, indent=4, ensure_ascii=False)

    def load_customers(self):
        if os.path.exists(CUSTOMERS_FILE):
            try:
                with open(CUSTOMERS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_customers(self):
        with open(CUSTOMERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.customers, f, indent=4, ensure_ascii=False)

    def calculate_quote_totals(self, items, discount_pct):
        subtotal = 0.0
        for item in items:
            for op in item.get("operations", []):
                subtotal += float(op.get("cost", 0))
                
        discount_amt = subtotal * (discount_pct / 100.0)
        net_total = subtotal - discount_amt
        vat_rate = self.settings.get("VAT_Rate", 20.0)
        vat_amt = net_total * (vat_rate / 100.0)
        gross_total = net_total + vat_amt
        
        return subtotal, discount_amt, net_total, vat_amt, gross_total

    def create_widgets(self):
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        tk.Button(btn_frame, text="Add Quote", command=self.add_quote, width=15, bg="#4CAF50", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Edit Quote", command=self.edit_quote, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Delete Quote", command=self.delete_quote, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="🖨 Generate PDF", command=self.generate_pdf, width=15, bg="#FF9800", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="⚙ Settings", command=self.open_settings_window, width=15).pack(side=tk.RIGHT, padx=5)

        columns = ("number", "customer", "name", "gross_total")
        self.tree = ttk.Treeview(self.root, columns=columns, show="headings")
        self.tree.heading("number", text="No.")
        self.tree.heading("customer", text="Customer")
        self.tree.heading("name", text="Quote Description")
        self.tree.heading("gross_total", text="Gross Total (£/$)")
        
        self.tree.column("number", width=50, anchor=tk.CENTER)
        self.tree.column("customer", width=200)
        self.tree.column("name", width=250)
        self.tree.column("gross_total", width=120, anchor=tk.E)
        
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.tree.bind("<Double-1>", lambda event: self.edit_quote())

    def refresh_list(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for q in self.quotes:
            discount_pct = float(q.get("discount", 0.0))
            
            items = q.get("items", [])
            if not items and "operations" in q:
                items = [{"operations": q["operations"]}]
                
            _, _, _, _, gross_total = self.calculate_quote_totals(items, discount_pct)
            
            customer_name = q.get("customer", {}).get("name", q.get("customer", "Unknown")) if isinstance(q.get("customer"), dict) else q.get("customer", "")
            self.tree.insert("", tk.END, values=(q["number"], customer_name, q.get("name", ""), f"{gross_total:.2f}"))

    def open_settings_window(self):
        win = tk.Toplevel(self.root)
        win.title("Settings - Rates & VAT")
        win.geometry("340x350")
        win.grab_set()

        entries = {}
        row = 0
        for key, val in self.settings.items():
            if key == "VAT_Rate":
                label_text = "VAT Rate (%):"
            elif key == "Starting_Quote_No":
                label_text = "Starting Quote No.:"
            else:
                label_text = f"{key} Rate:"
                
            tk.Label(win, text=label_text).grid(row=row, column=0, padx=20, pady=10, sticky="e")
            ent = tk.Entry(win, width=10)
            ent.insert(0, str(val))
            ent.grid(row=row, column=1, pady=10)
            entries[key] = ent
            row += 1

        def save_rates():
            for key, ent in entries.items():
                try:
                    if key == "Starting_Quote_No":
                        val = int(ent.get())
                    else:
                        val = float(ent.get().replace(',', '.'))
                    self.settings[key] = val
                except ValueError:
                    messagebox.showerror("Error", f"Invalid value for {key}", parent=win)
                    return
            self.save_settings()
            self.refresh_list()
            messagebox.showinfo("Success", "Settings saved successfully.", parent=win)
            win.destroy()

        tk.Button(win, text="Save Settings", command=save_rates, bg="#2196F3", fg="white").grid(row=row, columnspan=2, pady=20)

    # ================= ITEM SUB-WINDOW =================
    def open_item_window(self, parent_win, item_list, refresh_callback, item_index=None):
        win = tk.Toplevel(parent_win)
        win.title("Item Details & Operations")
        win.geometry("700x550")
        win.grab_set()

        is_editing = item_index is not None
        item_data = item_list[item_index] if is_editing else {}
        
        temp_operations = list(item_data.get("operations", []))

        info_frame = tk.Frame(win)
        info_frame.pack(fill=tk.X, padx=15, pady=10)

        tk.Label(info_frame, text="Item Name (e.g. Top SUB):").grid(row=0, column=0, sticky="e", pady=5)
        ent_item_name = tk.Entry(info_frame, width=40)
        ent_item_name.grid(row=0, column=1, padx=10, pady=5)

        tk.Label(info_frame, text="Required Date:").grid(row=1, column=0, sticky="e", pady=5)
        ent_req_date = tk.Entry(info_frame, width=20)
        ent_req_date.grid(row=1, column=1, sticky="w", padx=10, pady=5)

        if is_editing:
            ent_item_name.insert(0, item_data.get("name", ""))
            ent_req_date.insert(0, item_data.get("req_date", ""))

        op_frame = tk.LabelFrame(win, text="Machining Processes for this Item")
        op_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        add_op_frame = tk.Frame(op_frame)
        add_op_frame.pack(fill=tk.X, pady=10, padx=5)

        tk.Label(add_op_frame, text="Operation:").pack(side=tk.LEFT, padx=(0, 5))
        
        op_types = [k for k in self.settings.keys() if k not in ("VAT_Rate", "Starting_Quote_No")]
        cb_type = ttk.Combobox(add_op_frame, values=op_types, state="readonly", width=15)
        cb_type.pack(side=tk.LEFT, padx=5)
        if op_types: cb_type.current(0)

        tk.Label(add_op_frame, text="Time [h]:").pack(side=tk.LEFT, padx=(10, 5))
        ent_time = tk.Entry(add_op_frame, width=10)
        ent_time.pack(side=tk.LEFT, padx=5)

        columns_op = ("type", "time", "rate", "cost")
        op_tree = ttk.Treeview(op_frame, columns=columns_op, show="headings", height=6)
        op_tree.heading("type", text="Operation Type")
        op_tree.heading("time", text="Time (h)")
        op_tree.heading("rate", text="Rate (/h)")
        op_tree.heading("cost", text="Cost")
        
        op_tree.column("type", width=150)
        op_tree.column("time", width=100, anchor=tk.CENTER)
        op_tree.column("rate", width=100, anchor=tk.CENTER)
        op_tree.column("cost", width=120, anchor=tk.E)
        
        op_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        lbl_item_total = tk.Label(op_frame, text="Item Total: 0.00", font=("Arial", 10, "bold"))
        lbl_item_total.pack(side=tk.RIGHT, padx=10, pady=5)

        def refresh_operations():
            for row in op_tree.get_children():
                op_tree.delete(row)
            
            item_total = 0.0
            for op in temp_operations:
                item_total += float(op["cost"])
                op_tree.insert("", tk.END, values=(op["type"], f"{op['time']:.2f}", f"{op['rate']:.2f}", f"{op['cost']:.2f}"))
            
            lbl_item_total.config(text=f"Item Total: {item_total:.2f}")

        def add_operation():
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
            refresh_operations()
            ent_time.delete(0, tk.END)

        def delete_operation():
            selected = op_tree.focus()
            if not selected:
                return
            idx = op_tree.index(selected)
            del temp_operations[idx]
            refresh_operations()
            
        def edit_operation_on_double_click(event):
            selected = op_tree.focus()
            if not selected:
                return
            idx = op_tree.index(selected)
            op = temp_operations.pop(idx)
            
            cb_type.set(op["type"])
            ent_time.delete(0, tk.END)
            ent_time.insert(0, str(op["time"]))
            refresh_operations()

        op_tree.bind("<Double-1>", edit_operation_on_double_click)

        tk.Button(add_op_frame, text="Add Operation", command=add_operation).pack(side=tk.LEFT, padx=20)
        tk.Button(op_frame, text="Delete Selected Operation", command=delete_operation).pack(side=tk.LEFT, pady=5, anchor="w", padx=10)

        refresh_operations()

        def save_item():
            i_name = ent_item_name.get().strip()
            if not i_name:
                messagebox.showwarning("Error", "Item Name is required!", parent=win)
                return

            new_item_data = {
                "name": i_name,
                "req_date": ent_req_date.get().strip(),
                "operations": temp_operations
            }

            if is_editing:
                item_list[item_index] = new_item_data
            else:
                item_list.append(new_item_data)
                
            refresh_callback()
            win.destroy()

        tk.Button(win, text="Save Item to Quote", command=save_item, width=20, bg="#2196F3", fg="white", font=("Arial", 10, "bold")).pack(pady=15)

    # ================= QUOTE WINDOW =================
    def open_quote_window(self, quote_data=None):
        window = tk.Toplevel(self.root)
        window.title("Quote Details")
        window.geometry("850x750")
        window.grab_set()

        if quote_data is None:
            starting_num = int(self.settings.get("Starting_Quote_No", 1))
            if not self.quotes:
                new_number = starting_num
            else:
                max_current = max([int(q["number"]) for q in self.quotes])
                new_number = max(starting_num, max_current + 1)
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
                    "operations": list(quote_data["operations"])
                }]
        
        var_discount = tk.StringVar(value=str(quote_data.get("discount", 0.0)) if quote_data else "0")

        top_frame = tk.Frame(window)
        top_frame.pack(fill=tk.X, padx=15, pady=5)
        tk.Label(top_frame, text=f"QUOTE NO: {new_number}", font=("Arial", 14, "bold")).pack(side=tk.LEFT)
        
        tk.Label(top_frame, text="Quote Description: ").pack(side=tk.LEFT, padx=(20, 5))
        ent_quote_name = tk.Entry(top_frame, width=40)
        ent_quote_name.pack(side=tk.LEFT)
        if quote_data: ent_quote_name.insert(0, quote_data.get("name", ""))

        customer_frame = tk.LabelFrame(window, text="Customer Details")
        customer_frame.pack(fill=tk.X, padx=15, pady=10)

        tk.Label(customer_frame, text="Company Name:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        
        cb_cust_name = ttk.Combobox(customer_frame, width=32)
        cb_cust_name['values'] = list(self.customers.keys())
        cb_cust_name.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(customer_frame, text="Address:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        ent_cust_addr = tk.Entry(customer_frame, width=35)
        ent_cust_addr.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(customer_frame, text="Contact Person:").grid(row=0, column=2, sticky="e", padx=(20,5), pady=5)
        ent_cust_contact = tk.Entry(customer_frame, width=25)
        ent_cust_contact.grid(row=0, column=3, padx=5, pady=5)

        tk.Label(customer_frame, text="Phone Number:").grid(row=1, column=2, sticky="e", padx=(20,5), pady=5)
        ent_cust_phone = tk.Entry(customer_frame, width=25)
        ent_cust_phone.grid(row=1, column=3, padx=5, pady=5)

        def fill_customer_details(event=None):
            c_name = cb_cust_name.get().strip()
            if c_name in self.customers:
                c_data = self.customers[c_name]
                
                ent_cust_addr.delete(0, tk.END)
                ent_cust_addr.insert(0, c_data.get("address", ""))
                
                ent_cust_contact.delete(0, tk.END)
                ent_cust_contact.insert(0, c_data.get("contact", ""))
                
                ent_cust_phone.delete(0, tk.END)
                ent_cust_phone.insert(0, c_data.get("phone", ""))

        cb_cust_name.bind("<<ComboboxSelected>>", fill_customer_details)
        cb_cust_name.bind("<FocusOut>", fill_customer_details)

        if quote_data:
            cd = quote_data.get("customer", {})
            if isinstance(cd, dict):
                cb_cust_name.set(cd.get("name", ""))
                ent_cust_addr.insert(0, cd.get("address", ""))
                ent_cust_contact.insert(0, cd.get("contact", ""))
                ent_cust_phone.insert(0, cd.get("phone", ""))
            else:
                cb_cust_name.set(str(cd))

        items_frame = tk.LabelFrame(window, text="Items to Quote (Parts)")
        items_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        btn_items_frame = tk.Frame(items_frame)
        btn_items_frame.pack(fill=tk.X, pady=5, padx=5)

        columns_items = ("name", "req_date", "cost")
        items_tree = ttk.Treeview(items_frame, columns=columns_items, show="headings", height=5)
        items_tree.heading("name", text="Item Name")
        items_tree.heading("req_date", text="Required Date")
        items_tree.heading("cost", text="Item Total Cost")
        
        items_tree.column("name", width=300)
        items_tree.column("req_date", width=150, anchor=tk.CENTER)
        items_tree.column("cost", width=150, anchor=tk.E)
        
        items_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        totals_frame = tk.Frame(items_frame)
        totals_frame.pack(side=tk.RIGHT, padx=10, pady=10)

        tk.Label(totals_frame, text="Discount (%):").grid(row=0, column=0, sticky="e", pady=2)
        ent_discount = tk.Entry(totals_frame, width=8, textvariable=var_discount, justify="right")
        ent_discount.grid(row=0, column=1, sticky="e", pady=2)

        lbl_subtotal = tk.Label(totals_frame, text="Subtotal: 0.00")
        lbl_subtotal.grid(row=1, column=0, columnspan=2, sticky="e", pady=2)

        lbl_net = tk.Label(totals_frame, text="Net Total: 0.00")
        lbl_net.grid(row=2, column=0, columnspan=2, sticky="e", pady=2)

        lbl_vat = tk.Label(totals_frame, text="VAT Amount: 0.00")
        lbl_vat.grid(row=3, column=0, columnspan=2, sticky="e", pady=2)

        lbl_gross = tk.Label(totals_frame, text="Gross Total: 0.00", font=("Arial", 11, "bold"))
        lbl_gross.grid(row=4, column=0, columnspan=2, sticky="e", pady=5)

        def refresh_items_and_totals(*args):
            for row in items_tree.get_children():
                items_tree.delete(row)
            
            for idx, item in enumerate(temp_items):
                item_cost = sum(float(op["cost"]) for op in item.get("operations", []))
                items_tree.insert("", tk.END, iid=str(idx), values=(item.get("name", ""), item.get("req_date", ""), f"{item_cost:.2f}"))
            
            try:
                discount_val = float(var_discount.get().replace(',', '.') or 0)
            except ValueError:
                discount_val = 0.0

            subtotal, discount_amt, net_total, vat_amt, gross_total = self.calculate_quote_totals(temp_items, discount_val)
            vat_rate = self.settings.get("VAT_Rate", 20.0)

            lbl_subtotal.config(text=f"Subtotal: {subtotal:.2f}")
            lbl_net.config(text=f"Net Total: {net_total:.2f}")
            lbl_vat.config(text=f"VAT ({vat_rate}%): {vat_amt:.2f}")
            lbl_gross.config(text=f"Gross Total: {gross_total:.2f}")

        var_discount.trace_add("write", refresh_items_and_totals)

        def add_item_cmd():
            self.open_item_window(window, temp_items, refresh_items_and_totals)

        def edit_item_cmd(event=None):
            selected = items_tree.focus()
            if not selected:
                return
            idx = int(selected)
            self.open_item_window(window, temp_items, refresh_items_and_totals, item_index=idx)

        def delete_item_cmd():
            selected = items_tree.focus()
            if not selected:
                return
            idx = int(selected)
            del temp_items[idx]
            refresh_items_and_totals()

        tk.Button(btn_items_frame, text="Add New Item", command=add_item_cmd).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_items_frame, text="Edit Selected Item", command=edit_item_cmd).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_items_frame, text="Delete Item", command=delete_item_cmd).pack(side=tk.LEFT, padx=5)

        items_tree.bind("<Double-1>", edit_item_cmd)

        refresh_items_and_totals()

        def save():
            q_name = ent_quote_name.get().strip()
            cust_name = cb_cust_name.get().strip()

            if not cust_name or not q_name:
                messagebox.showwarning("Error", "'Company Name' and 'Quote Description' fields are required!", parent=window)
                return
                
            try:
                discount_val = float(var_discount.get().replace(',', '.') or 0)
            except ValueError:
                messagebox.showwarning("Error", "Discount must be a valid number!", parent=window)
                return

            cust_address = ent_cust_addr.get().strip()
            cust_contact = ent_cust_contact.get().strip()
            cust_phone = ent_cust_phone.get().strip()

            self.customers[cust_name] = {
                "address": cust_address,
                "contact": cust_contact,
                "phone": cust_phone
            }
            self.save_customers()
            
            cb_cust_name['values'] = list(self.customers.keys())

            new_data = {
                "number": new_number,
                "name": q_name,
                "discount": discount_val,
                "customer": {
                    "name": cust_name,
                    "address": cust_address,
                    "contact": cust_contact,
                    "phone": cust_phone
                },
                "items": temp_items
            }

            if quote_data is None:
                self.quotes.append(new_data)
            else:
                quote_data.update(new_data)
                if "operations" in quote_data:
                    del quote_data["operations"]

            self.save_data()
            self.refresh_list()
            window.destroy()

        tk.Button(window, text="Save Quote", command=save, width=20, bg="#4CAF50", fg="white", font=("Arial", 11, "bold")).pack(pady=15)

    def add_quote(self):
        self.open_quote_window()

    def edit_quote(self):
        selected = self.tree.focus()
        if not selected:
            messagebox.showinfo("Information", "Select a quote from the list to edit.")
            return
        
        values = self.tree.item(selected, "values")
        number = int(values[0])
        
        quote_data = next((q for q in self.quotes if q["number"] == number), None)
        if quote_data:
            self.open_quote_window(quote_data)

    def delete_quote(self):
        selected = self.tree.focus()
        if not selected:
            messagebox.showinfo("Information", "Select a quote from the list to delete.")
            return

        if messagebox.askyesno("Confirmation", "Are you sure you want to delete this quote?"):
            values = self.tree.item(selected, "values")
            number = int(values[0])
            
            self.quotes = [q for q in self.quotes if q["number"] != number]
            self.save_data()
            self.refresh_list()

    # ================= PDF GENERATION =================
    def generate_pdf(self):
        if FPDF is None:
            messagebox.showerror("Error", "FPDF library not installed.\nPlease run: pip install fpdf")
            return
            
        selected = self.tree.focus()
        if not selected:
            messagebox.showinfo("Information", "Select a quote from the list to generate PDF.")
            return
            
        values = self.tree.item(selected, "values")
        number = int(values[0])
        quote_data = next((q for q in self.quotes if q["number"] == number), None)
        
        if not quote_data:
            return

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=10)
        
        start_y = pdf.get_y()
        
        # Prawy górny róg - Dane firmy
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 5, "DM CNC Machining", ln=1, align="R")
        pdf.set_font("Arial", '', 10)
        pdf.cell(0, 5, "Aberdeen", ln=1, align="R")
        pdf.cell(0, 5, "Aberdeenshire", ln=1, align="R")
        
        # Lewa strona - Dane klienta
        pdf.set_y(start_y)
        cust = quote_data.get("customer", {})
        if isinstance(cust, dict):
            c_name = cust.get("name", "")
            c_addr = cust.get("address", "")
            c_contact = cust.get("contact", "")
            c_phone = cust.get("phone", "")
        else:
            c_name = str(cust)
            c_addr = ""
            c_contact = ""
            c_phone = ""

        pdf.set_font("Arial", 'B', 10)
        pdf.cell(100, 5, "BillTo:", ln=1)
        pdf.set_font("Arial", '', 10)
        if c_name: pdf.cell(100, 5, c_name, ln=1)
        if c_addr: pdf.cell(100, 5, c_addr, ln=1)
        if c_contact: pdf.cell(100, 5, f"Attn: {c_contact}", ln=1)
        if c_phone: pdf.cell(100, 5, f"Ph: {c_phone}", ln=1)
        
        pdf.ln(15)
        
        # Środek - Numer i opisy
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, f"QUOTE NO: {quote_data['number']}", ln=1, align="C")
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 8, quote_data.get("name", ""), ln=1, align="C")
        
        pdf.ln(10)
        
        # Tabela Items (Ceny bez VAT)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(90, 8, "Item Description", border=1, align="C")
        pdf.cell(50, 8, "Required Date", border=1, align="C")
        pdf.cell(50, 8, "Price (Net)", border=1, align="C")
        pdf.ln()
        
        pdf.set_font("Arial", '', 10)
        items = quote_data.get("items", [])
        if not items and "operations" in quote_data:
            items = [{"name": "Main Part", "req_date": "", "operations": quote_data["operations"]}]
            
        for item in items:
            item_cost = sum(float(op["cost"]) for op in item.get("operations", []))
            pdf.cell(90, 8, f" {item.get('name', '')}", border=1)
            pdf.cell(50, 8, item.get("req_date", ""), border=1, align="C")
            pdf.cell(50, 8, f"{item_cost:.2f}", border=1, align="R")
            pdf.ln()
            
        pdf.ln(10)
        
        # Podsumowanie i VAT
        discount_pct = float(quote_data.get("discount", 0.0))
        subtotal, discount_amt, net_total, vat_amt, gross_total = self.calculate_quote_totals(items, discount_pct)
        vat_rate = self.settings.get("VAT_Rate", 20.0)
        
        summary_x = 120
        pdf.set_x(summary_x)
        pdf.cell(40, 6, "Subtotal:")
        pdf.cell(30, 6, f"{subtotal:.2f}", align="R", ln=1)
        
        if discount_pct > 0:
            pdf.set_x(summary_x)
            pdf.cell(40, 6, f"Discount ({discount_pct}%):")
            pdf.cell(30, 6, f"-{discount_amt:.2f}", align="R", ln=1)
            
            pdf.set_x(summary_x)
            pdf.cell(40, 6, "Net Total:")
            pdf.cell(30, 6, f"{net_total:.2f}", align="R", ln=1)
            
        pdf.set_x(summary_x)
        pdf.cell(40, 6, f"VAT ({vat_rate}%):")
        pdf.cell(30, 6, f"{vat_amt:.2f}", align="R", ln=1)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.set_x(summary_x)
        pdf.cell(40, 8, "Gross Total:")
        pdf.cell(30, 8, f"{gross_total:.2f}", align="R", ln=1)
        
        filename = f"Quote_{quote_data['number']}.pdf"
        try:
            pdf.output(filename)
            messagebox.showinfo("Success", f"PDF generated successfully as:\n{filename}")
            os.startfile(filename)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save PDF:\n{str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = CncQuotesApp(root)
    root.mainloop()