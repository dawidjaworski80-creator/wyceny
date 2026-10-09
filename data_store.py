import json
import os
from typing import Any, Dict, List


class DataStore:
    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.data_file = os.path.join(self.base_dir, "quotes_data.json")
        self.settings_file = os.path.join(self.base_dir, "cnc_settings.json")
        self.customers_file = os.path.join(self.base_dir, "customers_data.json")
        self.suppliers_file = os.path.join(self.base_dir, "suppliers_data.json")

    def _load_json(self, file_path: str, default: Any):
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default
        return default

    def _save_json(self, file_path: str, data: Any):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def load_data(self) -> List[Dict[str, Any]]:
        return self._load_json(self.data_file, [])

    def save_data(self, quotes: List[Dict[str, Any]]):
        self._save_json(self.data_file, quotes)

    def load_settings(self) -> Dict[str, Any]:
        default_rates = {
            "Turning": 50.0,
            "Milling": 55.0,
            "Phosphate": 30.0,
            "Blasting": 25.0,
            "VAT_Rate": 20.0,
            "Starting_Quote_No": 1,
            "Starting_Order_No": 1,
            "Starting_Delivery_Note_No": 1,
            "Software_End_Date": "",
            "Company_Name": "247 Machining Services Ltd.",
            "Company_Address": "Aberdeenshire",
            "Company_Postcode": "AB21 0TZ",
            "Company_Reg_No": "",
            "VAT_Reg_No": "",
            "Company_Phone_Landline": "",
            "Company_Phone_Mobile": "",
        }
        saved = self._load_json(self.settings_file, {})
        default_rates.update(saved)
        return default_rates

    def save_settings(self, settings: Dict[str, Any]):
        self._save_json(self.settings_file, settings)

    def load_customers(self) -> Dict[str, Dict[str, str]]:
        return self._load_json(self.customers_file, {})

    def save_customers(self, customers: Dict[str, Dict[str, str]]):
        self._save_json(self.customers_file, customers)

    def load_suppliers(self) -> Dict[str, Dict[str, str]]:
        suppliers = self._load_json(self.suppliers_file, [])
        normalized: Dict[str, Dict[str, str]] = {}
        if isinstance(suppliers, list):
            for supplier in suppliers:
                name = str(supplier).strip()
                if name:
                    normalized[name] = {"address": "", "contact": ""}
        elif isinstance(suppliers, dict):
            for raw_name, details in suppliers.items():
                name = str(raw_name).strip()
                if not name:
                    continue
                if isinstance(details, dict):
                    normalized[name] = {
                        "address": str(details.get("address", "")),
                        "contact": str(details.get("contact", "")),
                    }
                else:
                    normalized[name] = {"address": "", "contact": ""}
        return dict(sorted(normalized.items(), key=lambda item: item[0].casefold()))

    def save_suppliers(self, suppliers: Dict[str, Dict[str, str]]):
        normalized = {
            name.strip(): {
                "address": str(details.get("address", "")),
                "contact": str(details.get("contact", "")),
            }
            for name, details in suppliers.items()
            if name.strip()
        }
        self._save_json(
            self.suppliers_file,
            dict(sorted(normalized.items(), key=lambda item: item[0].casefold())),
        )
