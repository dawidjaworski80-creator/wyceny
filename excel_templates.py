import atexit
import json
import math
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
from datetime import date, datetime

from data_store import clean_address

_worker = None
_script_directory = None
_worker_lock = threading.Lock()


DOCUMENT_LABELS = {
    "quote": "quote",
    "delivery_note": "delivery note",
    "job_card": "job card",
    "order_acknowledgment": "order acknowledgment",
}

POWERSHELL_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$excel = $null
$script:moneyKeys = @(
    'unit_price', 'line_total', 'material_unit_cost', 'item_material_cost',
    'subtotal', 'discount_amount', 'net_total', 'vat_amount', 'grand_total',
    'operation_rate', 'operation_cost'
)

function ConvertTo-Map($Object) {
    $result = @{}
    if ($null -ne $Object) {
        foreach ($property in $Object.PSObject.Properties) {
            $result[$property.Name] = $property.Value
        }
    }
    return $result
}

function Get-RangeValues($Range) {
    $value = $Range.Value2
    if ($value -is [array]) { return ,$value }
    $single = New-Object 'object[,]' 1, 1
    $single[0, 0] = $value
    return ,$single
}

function Set-CellTokens($Cell, $Value, $Tokens) {
    $matches = [regex]::Matches($Value, '\{\{([a-zA-Z0-9_]+)\}\}')
    if ($matches.Count -eq 1 -and $matches[0].Value -eq $Value) {
        $key = $matches[0].Groups[1].Value
        if ($Tokens.ContainsKey($key)) {
            $replacement = $Tokens[$key]
            if ($null -eq $replacement) {
                $Cell.Value2 = ''
            }
            elseif ($replacement -is [string]) {
                $Cell.NumberFormat = '@'
                $Cell.Value2 = $replacement
            }
            else {
                if ($script:moneyKeys -contains $key) {
                    $Cell.NumberFormat = '0.00'
                }
                $Cell.Formula = [string]$replacement
            }
        }
        return
    }
    $updated = $Value
    foreach ($match in $matches) {
        $key = $match.Groups[1].Value
        if ($Tokens.ContainsKey($key)) {
            $updated = $updated.Replace($match.Value, [string]$Tokens[$key])
        }
    }
    if ($updated -ne $Value) { $Cell.Value2 = $updated }
}

function Replace-RangeTokens($Sheet, $Range, $Tokens) {
    $values = Get-RangeValues $Range
    $firstRow = [int]$Range.Row
    $firstColumn = [int]$Range.Column
    $rowStart = $values.GetLowerBound(0)
    $columnStart = $values.GetLowerBound(1)
    for ($r = $rowStart; $r -le $values.GetUpperBound(0); $r++) {
        for ($c = $columnStart; $c -le $values.GetUpperBound(1); $c++) {
            $value = $values[$r, $c]
            if ($value -isnot [string] -or $value.IndexOf('{{') -lt 0) { continue }
            $cell = $Sheet.Cells.Item($firstRow + $r - $rowStart, $firstColumn + $c - $columnStart)
            Set-CellTokens $cell $value $Tokens
        }
    }
}

function Replace-RowTokens($Sheet, [int]$Row, $Tokens) {
    $used = $Sheet.UsedRange
    $lastColumn = $used.Column + $used.Columns.Count - 1
    $range = $Sheet.Range($Sheet.Cells.Item($Row, 1), $Sheet.Cells.Item($Row, $lastColumn))
    Replace-RangeTokens $Sheet $range $Tokens
}

function Find-TableMarker($Sheet, [string]$Marker) {
    $used = $Sheet.UsedRange
    $values = Get-RangeValues $used
    $rowStart = $values.GetLowerBound(0)
    $columnStart = $values.GetLowerBound(1)
    for ($r = $rowStart; $r -le $values.GetUpperBound(0); $r++) {
        for ($c = $columnStart; $c -le $values.GetUpperBound(1); $c++) {
            if ([string]$values[$r, $c] -ceq $Marker) {
                return ([int]$used.Row + $r - $rowStart)
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
    Replace-RangeTokens $Sheet $Sheet.UsedRange $Tokens
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
    $values = Get-RangeValues $Sheet.UsedRange
    foreach ($value in $values) {
        if ($value -is [string] -and $value.IndexOf('{{') -ge 0) {
            foreach ($match in [regex]::Matches($value, '\{\{[^{}]+\}\}')) {
                $tokens += $match.Value
            }
        }
    }
    return $tokens
}

function Initialize-Excel {
    if ($null -ne $script:excel) {
        try { $null = $script:excel.Version } catch { $script:excel = $null }
    }
    if ($null -eq $script:excel) {
        $script:excel = New-Object -ComObject Excel.Application
        $script:excel.Visible = $false
        $script:excel.DisplayAlerts = $false
        $script:excel.ScreenUpdating = $false
        $script:excel.EnableEvents = $false
    }
}

function Invoke-Document([string]$PayloadPath) {
$workbook = $null
$sheets = $null
$allSheets = $null
try {
    $payload = Get-Content -LiteralPath $PayloadPath -Encoding UTF8 -Raw | ConvertFrom-Json
    Initialize-Excel
    $workbook = $script:excel.Workbooks.Open($payload.template_path, 0, $false)
    $script:excel.Calculation = -4135
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
    $script:excel.CalculateFull()
    $workbook.ExportAsFixedFormat(0, $payload.output_path, 0, $true, $false)
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
        try { $workbook.Close($false) } catch { }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($workbook)
    }
}
}

try {
    while ($true) {
        $line = [Console]::In.ReadLine()
        if ($null -eq $line) { break }
        $line = $line.Trim()
        if (-not $line) { continue }
        try {
            if ($line -eq 'WARMUP') { Initialize-Excel }
            else { Invoke-Document $line }
            [Console]::Out.WriteLine('OK')
        }
        catch {
            $message = ($_.Exception.Message -replace '\s+', ' ')
            [Console]::Out.WriteLine('ERR ' + $message)
        }
    }
}
finally {
    if ($null -ne $excel) {
        try { $excel.Quit() } catch { }
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
    for item in items:
        if not str(item.get("req_date", "")).strip():
            item["req_date"] = data.get("required_date", "")
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
        "order_acknowledgment": "ORDER ACKNOWLEDGEMENT",
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
        "customer_address": clean_address(customer.get("address", "")),
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
        if len(items) > 1:
            values["order_number"] = f"{common_values.get('order_number', '')}/{index}"
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


def _stop_worker():
    global _worker
    worker, _worker = _worker, None
    if worker is None:
        return
    process = worker[0]
    try:
        process.stdin.close()
    except OSError:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _ensure_worker():
    global _worker, _script_directory
    if _worker is not None and _worker[0].poll() is None:
        return _worker
    _worker = None
    import shutil

    powershell = shutil.which("powershell.exe")
    if not powershell:
        raise RuntimeError("Windows PowerShell is required to export Excel templates to PDF.")
    if _script_directory is None:
        _script_directory = tempfile.mkdtemp(prefix="wyceny_excel_worker_")
        atexit.register(shutil.rmtree, _script_directory, True)
    script_path = os.path.join(_script_directory, "worker.ps1")
    with open(script_path, "w", encoding="utf-8") as script_file:
        script_file.write(POWERSHELL_SCRIPT)
    process = subprocess.Popen(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script_path,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    responses = queue.Queue()

    def read_responses():
        for raw_line in iter(process.stdout.readline, b""):
            responses.put(raw_line.decode("utf-8-sig", "replace").strip())
        responses.put(None)

    threading.Thread(target=read_responses, daemon=True).start()
    _worker = (process, responses)
    return _worker


def _worker_request(line, timeout):
    with _worker_lock:
        process, responses = _ensure_worker()
        try:
            process.stdin.write((line + "\n").encode("utf-8"))
            process.stdin.flush()
        except OSError as exc:
            _stop_worker()
            raise RuntimeError("The Excel export process stopped unexpectedly.") from exc
        try:
            response = responses.get(timeout=timeout)
        except queue.Empty:
            process.kill()
            _stop_worker()
            raise RuntimeError("Excel took too long to export the document to PDF.")
        if response is None:
            _stop_worker()
            raise RuntimeError("The Excel export process stopped unexpectedly.")
        return response


def prewarm_excel():
    """Starts the hidden Excel instance in the background so the first PDF is fast."""

    def warm_up():
        try:
            _worker_request("WARMUP", timeout=120)
        except RuntimeError:
            pass

    threading.Thread(target=warm_up, daemon=True).start()


atexit.register(_stop_worker)


def generate_excel_document(document_type, data, settings):
    if document_type not in DOCUMENT_LABELS:
        raise RuntimeError(f"Unknown Excel document type: {document_type}")
    if document_type != "quote" and data.get("status") != "order":
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
    if not os.path.isabs(template_path):
        base = (
            os.path.dirname(sys.executable)
            if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__))
        )
        template_path = os.path.join(base, template_path)
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
        "order_acknowledgment": "Order_Acknowledgement",
    }[document_type]
    filename = f"{prefix}_{_safe_number(number)}.pdf"
    folder_key = {
        "quote": "Quotes_Folder",
        "delivery_note": "Delivery_Notes_Folder",
        "order_acknowledgment": "Acknowledgments_Folder",
    }.get(document_type)
    output_directory = str(settings.get(folder_key, "")).strip() if folder_key else ""
    output_directory = output_directory or str(settings.get("Pdf_Output_Directory", "")).strip()
    if output_directory and not os.path.isdir(output_directory):
        raise RuntimeError(f"PDF save folder does not exist: {output_directory}")
    output_path = os.path.abspath(os.path.join(output_directory or os.getcwd(), filename))
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except OSError:
            # The previous PDF is still open in a viewer; save under a new name.
            stem, extension = os.path.splitext(output_path)
            output_path = f"{stem}_{datetime.now().strftime('%H%M%S')}{extension}"

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

    with tempfile.TemporaryDirectory(prefix="wyceny_excel_") as temporary_directory:
        payload_path = os.path.join(temporary_directory, "document.json")
        with open(payload_path, "w", encoding="utf-8") as payload_file:
            json.dump(payload, payload_file, ensure_ascii=False)
        response = _worker_request(payload_path, timeout=120)

    if response != "OK":
        error = response[4:] if response.startswith("ERR ") else response
        raise RuntimeError(error.strip() or "Excel could not export the document.")
    if not os.path.isfile(output_path):
        raise RuntimeError("Excel reported success but the PDF file was not created.")
    return output_path
