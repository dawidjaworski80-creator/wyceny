from pdf_layouts import generate_layout_document


class PdfService:
    @staticmethod
    def generate_delivery_note(order_data: dict, settings: dict):
        return generate_layout_document("delivery_note", order_data, settings)

    @staticmethod
    def generate_job_card(order_data: dict, settings: dict):
        return generate_layout_document("job_card", order_data, settings)

    @staticmethod
    def generate_pdf(quote_data: dict, settings: dict):
        return generate_layout_document("quote", quote_data, settings)
