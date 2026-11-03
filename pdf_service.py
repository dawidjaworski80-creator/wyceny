from excel_templates import generate_excel_document


class PdfService:
    @staticmethod
    def generate_delivery_note(order_data: dict, settings: dict):
        return generate_excel_document("delivery_note", order_data, settings)

    @staticmethod
    def generate_job_card(order_data: dict, settings: dict):
        return generate_excel_document("job_card", order_data, settings)

    @staticmethod
    def generate_pdf(quote_data: dict, settings: dict):
        return generate_excel_document("quote", quote_data, settings)
