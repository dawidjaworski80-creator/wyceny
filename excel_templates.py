import json
import math
import os
import re
import subprocess
import tempfile
from datetime import date, datetime


DOCUMENT_LABELS = {
    "quote": "quote",
    "delivery_note": "delivery note",
    "job_card": "job card",
}

POWERSHELL_SCRIPT = r"""
param([string]$PayloadPath)
$ErrorActionPreference = 'Stop'
$excel = $null
$workbook = $null
$sheets = $null
$allSheets = $null

function ConvertTo-Map($Object) {
    $result = @{}
    if ($null -ne $Object) {
        foreach ($property in $Object.PSObject.Properties) {
            $result[$property.Name] = $property.Value
        }
    }
    return $result
}

function Replace-RowTokens($Sheet, [int]$Row, $Tokens) {
    $used = $Sheet.UsedRange
    $lastColumn = $used.Column + $used.Columns.Count - 1
    for ($column = 1; $column -le $lastColumn; $column++) {
        $cell = $Sheet.Cells.Item($Row, $column)
        $value = $cell.Value2
        if ($value -isnot [string]) { continue }
        $matches = [regex]::Matches($value, '\{\{([a-zA-Z0-9_]+)\}\}')
        if ($matches.Count -eq 1 -and $matches[0].Value -eq $value) {
            $key = $matches[0].Groups[1].Value
            if ($Tokens.ContainsKey($key)) {
                $replacement = $Tokens[$key]
                if ($null -eq $replacement) {
                    $cell.Value2 = ''
                }
                elseif ($replacement -is [string]) {
                    $cell.NumberFormat = '@'
                    $cell.Value2 = $replacement
                }
                else {
                    $cell.Formula = [string]$replacement
                }
            }
            continue
        }
        $updated = $value
        foreach ($match in $matches) {
            $key = $match.Groups[1].Value
            if ($Tokens.ContainsKey($key)) {
                $updated = $updated.Replace($match.Value, [string]$Tokens[$key])
            }
        }
        if ($updated -ne $value) { $cell.Value2 = $updated }
    }
}

function Find-TableMarker($Sheet, [string]$Marker) {
    $used = $Sheet.UsedRange
    $lastRow = $used.Row + $used.Rows.Count - 1
    $lastColumn = $used.Column + $used.Columns.Count - 1
    for ($row = $used.Row; $row -le $lastRow; $row++) {
        for ($column = $used.Column; $column -le $lastColumn; $column++) {
            if ([string]$Sheet.Cells.Item($row, $column).Value2 -ceq $Marker) {
                return $row
            }
        }
    }
    return $null
}

function Expand-Table($Sheet, [string]$Marker, $Records) {
    $tableRow = Find-TableMarker $Sheet $Marker
    if ($null -eq $tableRow) { return $false }
    $sourceRow = $Sheet.Rows.Item([int]$tableRow)
    for ($index = 1; $index -lt $Records.Count; $index++) {
        $Sheet.Rows.Item([int]$tableRow + $index).Insert()
        $sourceRow.Copy($Sheet.Rows.Item([int]$tableRow + $index))
    }
    if ($Records.Count -eq 0) {
        $emptyTokens = @{}
        $emptyTokens[$Marker.Trim('{}')] = ''
        Replace-RowTokens $Sheet ([int]$tableRow) $emptyTokens
        return $true
    }
    for ($index = 0; $index -lt $Records.Count; $index++) {
        $tokens = ConvertTo-Map $Records[$index]
        $tokens[$Marker.Trim('{}')] = ''
        Replace-RowTokens $Sheet ([int]$tableRow + $index) $tokens
    }
    return $true
}

function Replace-SheetTokens($Sheet, $Tokens) {
    $used = $Sheet.UsedRange
    $lastRow = $used.Row + $used.Rows.Count - 1
    $lastColumn = $used.Column + $used.Columns.Count - 1
    for ($row = $used.Row; $row -le $lastRow; $row++) {
        Replace-RowTokens $Sheet $row $Tokens
    }
}

function Expand-PrintAreaToUsedRows($Sheet) {
    $used = $Sheet.UsedRange
    $printArea = [string]$Sheet.PageSetup.PrintArea
    if ($printArea) {
        $printRange = $Sheet.Range($printArea)
        if ($printRange.Areas.Count -ne 1) {
            throw 'The template print area must be a single contiguous range.'
        }
    }
    else {
        $printRange = $used
    }
    $firstRow = [Math]::Min([int]$printRange.Row, [int]$used.Row)
    $lastRow = [Math]::Max(
        [int]($printRange.Row + $printRange.Rows.Count - 1),
        [int]($used.Row + $used.Rows.Count - 1)
    )
    $firstColumn = [int]$printRange.Column
    $lastColumn = [int]($printRange.Column + $printRange.Columns.Count - 1)
    $start = $Sheet.Cells.Item($firstRow, $firstColumn).Address($false, $false)
    $end = $Sheet.Cells.Item($lastRow, $lastColumn).Address($false, $false)
    $Sheet.PageSetup.PrintArea = "$start`:$end"
}

function Get-UnresolvedTokens($Sheet) {
    $tokens = @()
    $used = $Sheet.UsedRange
    $lastRow = $used.Row + $used.Rows.Count - 1
    $lastColumn = $used.Column + $used.Columns.Count - 1
    for ($row = $used.Row; $row -le $lastRow; $row++) {
        for ($column = $used.Column; $column -le $lastColumn; $column++) {
            $value = $Sheet.Cells.Item($row, $column).Value2
            if ($value -is [string]) {
                foreach ($match in [regex]::Matches($value, '\{\{[^{}]+\}\}')) {
                    $tokens += $match.Value
                }
            }
        }
    }
    return $tokens
}

try {
    $payload = Get-Content -LiteralPath $PayloadPath -Encoding UTF8 -Raw | ConvertFrom-Json
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $false
    $workbook = $excel.Workbooks.Open($payload.template_path, 0, $false)
    $worksheetCount = $workbook.Worksheets.Count

    if ($payload.document_type -eq 'job_card') {
        if ($worksheetCount -ne 1) {
            throw 'The job card template must contain exactly one worksheet.'
        }
        $baseSheet = $workbook.Worksheets.Item(1)
        $sheets = @($baseSheet)
        for ($index = 1; $index -lt $payload.job_cards.Count; $index++) {
            $baseSheet.Copy([Type]::Missing, $workbook.Worksheets.Item($workbook.Worksheets.Count))
            $sheets += $workbook.Worksheets.Item($workbook.Worksheets.Count)
        }
        for ($index = 0; $index -lt $payload.job_cards.Count; $index++) {
            $sheet = $sheets[$index]
            $sheet.Name = 'Item_' + ($index + 1)
            $jobCard = $payload.job_cards[$index]
            $tokens = ConvertTo-Map $jobCard.values
            $operationRows = @($jobCard.operations)
            if ($operationRows.Count -eq 0) {
                $operationRows = @([pscustomobject]@{
                    operation_number = ''
                    operation_name = ''
                    operation_time = ''
                    operation_rate = ''
                    operation_cost = ''
                })
            }
            if (-not (Expand-Table $sheet '{{operations_table}}' $operationRows)) {
                throw 'The job card template is missing the {{operations_table}} row marker.'
            }
            Replace-SheetTokens $sheet $tokens
            Expand-PrintAreaToUsedRows $sheet
        }
    }
    else {
        $allSheets = @()
        for ($index = 1; $index -le $worksheetCount; $index++) {
            $allSheets += $workbook.Worksheets.Item($index)
        }
        $tableMarker = '{{items_table}}'
        $tableCount = 0
        foreach ($sheet in $allSheets) {
            $tableRow = Find-TableMarker $sheet $tableMarker
            if ($null -ne $tableRow) {
                $tableCount++
                if (-not (Expand-Table $sheet $tableMarker $payload.items)) {
                    throw 'Could not expand the items table.'
                }
            }
        }
        if ($tableCount -ne 1) {
            throw 'The template must contain exactly one row with the {{items_table}} marker.'
        }
        $tokens = ConvertTo-Map $payload.values
        foreach ($sheet in $allSheets) {
            Replace-SheetTokens $sheet $tokens
            Expand-PrintAreaToUsedRows $sheet
        }
    }

    $unresolved = @()
    for ($index = 1; $index -le $workbook.Worksheets.Count; $index++) {
        $unresolved += Get-UnresolvedTokens $workbook.Worksheets.Item($index)
    }
    if ($unresolved.Count -gt 0) {
        $distinct = ($unresolved | Sort-Object -Unique) -join ', '
        throw "The template contains unknown or unsupported placeholders: $distinct"
    }
    $excel.CalculateFull()
    $workbook.ExportAsFixedFormat(0, $payload.output_path, 0, $true, $false)
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
finally {
    if ($null -ne $sheets) {
        foreach ($sheetReference in $sheets) {
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($sheetReference)
        }
    }
    if ($null -ne $allSheets) {
        foreach ($sheetReference in $allSheets) {
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($sheetReference)
        }
    }
    $sheet = $null
    $baseSheet = $null
    $sourceRow = $null
    $targetRow = $null
    if ($null -ne $workbook) {
        $workbook.Close($false)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($workbook)
    }
    if ($null -ne $excel) {
        $excel.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
"""


def _format_date(value):
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return value


def _get_items(data):
    items = [dict(item) for item in data.get("items", [])]
    if not items and "operations" in data:
        items = [{
            "name": data.get("name", "Main Part"),
            "drawing_number": data.get("drawing_number", ""),
            "revision": data.get("revision", ""),
            "quantity": 1,
            "req_date": data.get("required_date", ""),
            "material": data.get("material", ""),
            "material_cost": data.get("material_cost", 0),
            "supplier": data.get("supplier", ""),
            "cast": data.get("cast", ""),
            "mct_number": data.get("mct_number", ""),
            "operations": data["operations"],
        }]
    return items


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _item_values(item, index, legacy_markup=0.0):
    quantity = int(item.get("quantity", 1) or 1)
    material_cost = _number(item.get("material_cost"))
    operations = item.get("operations", [])
    unit_cost = material_cost + sum(_number(operation.get("cost")) for operation in operations)
    markup = _number(item.get("markup", legacy_markup))
    if not math.isfinite(markup) or markup < 0:
        markup = 0.0
    unit_price = unit_cost * (1 + markup / 100)
    return {
        "item_number": index,
        "item_name": str(item.get("name", "")),
        "drawing_number": str(item.get("drawing_number", "")),
        "revision": str(item.get("revision", "")),
        "quantity": quantity,
        "item_required_date": _format_date(item.get("req_date", "")),
        "material": str(item.get("material", "")),
        "supplier": str(item.get("supplier", "")),
        "material_unit_cost": material_cost,
        "unit_price": unit_price,
        "line_total": unit_price * quantity,
        "cast": str(item.get("cast", "")),
        "mct_number": str(item.get("mct_number", "")),
    }


def _common_values(document_type, data, settings):
    customer = data.get("customer", {})
    if not isinstance(customer, dict):
        customer = {"name": str(customer)}
    now = date.today().strftime("%d.%m.%Y")
    number = data.get("number", "")
    title = {
        "quote": f"{'ORDER' if data.get('status') == 'order' else 'QUOTE'} NO: {number}",
        "delivery_note": "CUSTOMER DELIVERY NOTE",
        "job_card": "ROUTE CARD",
    }[document_type]
    subtotal = 0.0
    for item in _get_items(data):
        row = _item_values(item, 1, _number(data.get("markup")))
        subtotal += row["line_total"]
    discount_percent = _number(data.get("discount"))
    discount_amount = subtotal * discount_percent / 100
    net_total = subtotal - discount_amount
    vat_rate = _number(settings.get("VAT_Rate", 20))
    vat_amount = net_total * vat_rate / 100
    values = {
        "document_title": title,
        "document_name": str(data.get("name", "")),
        "number": str(number),
        "quote_number": str(number),
        "order_number": str(number),
        "quote_date": now,
        "document_date": now,
        "required_date": _format_date(data.get("required_date", "")),
        "customer_name": str(customer.get("name", "")),
        "customer_address": str(customer.get("address", "")),
        "customer_contact": str(customer.get("contact", "")),
        "customer_phone": str(customer.get("phone", "")),
        "customer_email": str(customer.get("email", "")),
        "customer_po_number": str(data.get("customer_po_number", "")),
        "company_name": str(settings.get("Company_Name", "")),
        "company_address": str(settings.get("Company_Address", "")),
        "company_postcode": str(settings.get("Company_Postcode", "")),
        "company_reg_no": str(settings.get("Company_Reg_No", "")),
        "vat_reg_no": str(settings.get("VAT_Reg_No", "")),
        "company_phone_landline": str(settings.get("Company_Phone_Landline", "")),
        "company_phone_mobile": str(settings.get("Company_Phone_Mobile", "")),
        "delivery_note_number": str(data.get("delivery_note_number", "")),
        "order_status": str(data.get("order_status", "")),
        "document_status": "Order" if data.get("status") == "order" else "Quote",
        "job_card_date": now,
        "subtotal": subtotal,
        "discount_percent": discount_percent,
        "discount_amount": discount_amount,
        "net_total": net_total,
        "vat_rate": vat_rate,
        "vat_amount": vat_amount,
        "grand_total": net_total + vat_amount,
    }
    return values


def _build_job_cards(data, common_values):
    items = _get_items(data)
    legacy_markup = _number(data.get("markup"))
    cards = []
    for index, item in enumerate(items, start=1):
        item_values = _item_values(item, index, legacy_markup)
        values = dict(common_values)
        values.update(item_values)
        values["item_material_cost"] = item_values["material_unit_cost"]
        operation_rows = []
        for operation_index, operation in enumerate(item.get("operations", []), start=1):
            operation_rows.append({
                "operation_number": operation_index,
                "operation_name": str(operation.get("type", "")),
                "operation_time": _number(operation.get("time")),
                "operation_rate": _number(operation.get("rate")),
                "operation_cost": _number(operation.get("cost")),
            })
        cards.append({"values": values, "operations": operation_rows})
    return cards


def _safe_number(value):
    value = str(value or "Document").strip()
    return "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in value
    )


def generate_excel_document(document_type, data, settings):
    import shutil

    if document_type not in DOCUMENT_LABELS:
        raise RuntimeError(f"Unknown Excel document type: {document_type}")
    if document_type in ("delivery_note", "job_card") and data.get("status") != "order":
        raise RuntimeError(
            f"A {DOCUMENT_LABELS[document_type]} can only be generated for an order."
        )

    templates = settings.get("Excel_Templates", {})
    template_path = (
        str(templates.get(document_type, "")).strip()
        if isinstance(templates, dict)
        else ""
    )
    if not template_path:
        raise RuntimeError(
            f"Choose an Excel template for {DOCUMENT_LABELS[document_type]} "
            "in Settings > Excel Templates."
        )
    if not os.path.isfile(template_path):
        raise RuntimeError(f"The Excel template file does not exist: {template_path}")
    if os.path.splitext(template_path)[1].lower() != ".xlsx":
        raise RuntimeError("Excel templates must be .xlsx files.")

    if document_type == "job_card" and not _get_items(data):
        raise RuntimeError("This order has no items to include on a job card.")

    number = (
        data.get("delivery_note_number", data.get("number", "Document"))
        if document_type == "delivery_note"
        else data.get("number", "Document")
    )
    prefix = {
        "quote": "Quote",
        "delivery_note": "Delivery_Note",
        "job_card": "Job_Card",
    }[document_type]
    filename = f"{prefix}_{_safe_number(number)}.pdf"
    output_directory = str(settings.get("Pdf_Output_Directory", "")).strip()
    if output_directory and not os.path.isdir(output_directory):
        raise RuntimeError(f"PDF save folder does not exist: {output_directory}")
    output_path = os.path.abspath(os.path.join(output_directory or os.getcwd(), filename))

    common_values = _common_values(document_type, data, settings)
    payload = {
        "document_type": document_type,
        "template_path": os.path.abspath(template_path),
        "output_path": output_path,
    }
    if document_type == "job_card":
        payload["job_cards"] = _build_job_cards(data, common_values)
    else:
        items = _get_items(data)
        if not items:
            raise RuntimeError("This document has no items to include.")
        payload["values"] = common_values
        payload["items"] = [
            _item_values(item, index, _number(data.get("markup")))
            for index, item in enumerate(items, start=1)
        ]

    powershell = shutil.which("powershell.exe")
    if not powershell:
        raise RuntimeError("Windows PowerShell is required to export Excel templates to PDF.")

    with tempfile.TemporaryDirectory(prefix="wyceny_excel_") as temporary_directory:
        payload_path = os.path.join(temporary_directory, "document.json")
        script_path = os.path.join(temporary_directory, "export.ps1")
        with open(payload_path, "w", encoding="utf-8") as payload_file:
            json.dump(payload, payload_file, ensure_ascii=False)
        with open(script_path, "w", encoding="utf-8") as script_file:
            script_file.write(POWERSHELL_SCRIPT)
        try:
            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    script_path,
                    payload_path,
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Excel took too long to export the document to PDF.") from exc

    if result.returncode:
        error = (
            result.stderr.strip()
            or result.stdout.strip()
            or "Excel could not export the document."
        )
        raise RuntimeError(re.sub(r"\s+", " ", error))
    if not os.path.isfile(output_path):
        raise RuntimeError("Excel reported success but the PDF file was not created.")
    return output_path
