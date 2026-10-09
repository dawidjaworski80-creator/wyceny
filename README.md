# DM CNC Machining - Quoting System

Prosty system do wycen CNC z interfejsem Tkinter.

## Struktura projektu

- `main.py` - punkt wejścia aplikacji
- `app.py` - logika GUI i obsługa formularzy
- `data_store.py` - odczyt/zapis danych JSON
- `pdf_service.py` i `pdf_layouts.py` - generowanie PDF oraz edytowalne układy dokumentów

## Uruchomienie

```bash
python main.py
```

## Obsługa wycen i zamówień

- Górny pasek zawiera kolorowe przyciski **Home**, **Quotes**, **New Quote** i **Orders**.
- Po uruchomieniu widok **Home** pokazuje do 10 ostatnich zamówień.
- Wiersze na listach aplikacji oraz pozycje elementów na PDF-ie mają numerację.
- **Quotes** pokazuje zapisane wyceny.
- W widokach **Quotes** i **Orders** pasek wyszukiwania filtruje listę po nazwie wyceny/zamówienia lub klienta, nazwie pozycji, numerze rysunku, numerze quote/order albo Customer PO. Wpisz szukaną wartość i naciśnij **Search** lub Enter; **Clear** przywraca pełną listę.
- W **Quotes** przyciski **Copy Quote** i **Paste Quote** kopiują wybraną wycenę jako nową pozycję z kolejnym numerem. W formularzu wyceny przyciski **Copy Item** i **Paste Item** kopiują wybraną pozycję do użycia także w innej wycenie. Kopiowane elementy zachowują opis, operacje i materiał; nowa kopia nie dziedziczy zarejestrowanego czasu wykonania.
- **New Quote** otwiera formularz nowej wyceny; po zapisaniu pojawi się ona na liście Quotes.
- Każda wycena ma pola **Markup (%)** i **Discount (%)**. W zamówieniu te wartości są tylko do odczytu i pozostają takie, jak zapisano w wycenie. Markup jest dodawany do kosztu materiałów i operacji przed rabatem i VAT; ceny oraz sumy w aplikacji i PDF uwzględniają markup, ale PDF nie pokazuje jego wartości ani osobnej pozycji.
- W edytowalnych polach liczbowych, których wartość początkowa wynosi zero, kliknięcie pola czyści zero, aby można było od razu wpisać nową wartość.
- W polach opisowych pierwsza litera każdego wyrazu jest automatycznie zamieniana na wielką po opuszczeniu pola. E-maile, numery, daty i ścieżki nie są zmieniane.
- Klawisz **Enter** zatwierdza wpis i przechodzi do następnego pola formularza. W polach wielowierszowych **Shift+Enter** wstawia nową linię.
- W oknie **Add New Item** / **Edit Item** każda pozycja wyceny lub zamówienia ma własne pola **Drawing Number**, **Revision** i **Quantity**. Koszt oraz czas operacji są podawane za sztukę, a wartość pozycji i suma wyceny są mnożone przez ilość. Lista pozycji i PDF wyceny pokazują zarówno **Unit Price**, jak i **Line Total**; ilość jest widoczna także na liście przewozowym. Starsze pozycje bez zapisanej ilości są traktowane jako jedna sztuka.
- Formularz wyceny pozwala ustawić **Date Required** przez wybór konkretnego dnia z kalendarza albo terminu za 1–5 dni lub 1–5 tygodni. Data jest zapisywana z wyceną i widoczna w PDF.
- Otwórz zapisaną wycenę przez **Edit Quote**, aby użyć znajdujących się w jej oknie przycisków **Generate PDF** i **Email PDF**. Przyciskiem **Change to Order** można przenieść wycenę do **Orders**; zamówienie otrzyma kolejny numer z osobnej sekwencji konfigurowanej w **Settings > General > Orders Start No.** Numery ofert nadal korzystają z **Starting Quote No.**.
- **Orders** pokazuje wyceny zmienione na zamówienia. Przycisk **Change to Quote** tworzy nową wycenę na podstawie zaznaczonego zamówienia z kolejnym numerem; oryginalne zamówienie pozostaje na liście Orders. Nowa wycena nie zawiera statusu zamówienia, Customer PO Number ani zarejestrowanych czasów rzeczywistych.
- W zakładce **Orders** zaznacz zamówienie i wybierz **Generate JOB CARD**, aby utworzyć wielostronicowy PDF z osobną kartą dla każdej pozycji. Karta zawiera informacje o kliencie i zamówieniu, pozycję z rysunkiem i materiałem, wiersze operacji oraz dane surowca. Położenie i wygląd tych informacji można zmienić w **Settings > PDF Layout Generator**.
- Otwórz konkretne zamówienie przez **Edit Order**, aby wygenerować dla niego delivery note przyciskiem **Generate Delivery Note**. Dokument zawiera informacje o nadawcy, odbiorcy, numerach zamówienia i PO, dacie, pozycjach oraz pola podpisów. Układ każdego bloku można zmienić w **Settings > PDF Layout Generator**.
- Po otwarciu zamówienia przyciskiem **Edit Order** można ustawić jego status **Pending**, **Completed** lub **Invoiced**, wpisać **Customer PO Number** oraz zapisać rzeczywisty czas pracy całej partii osobno dla każdego itemu. Pozycję można zaznaczyć i otworzyć jej podgląd przyciskiem **View Selected Item** lub dwuklikiem, aby sprawdzić zaplanowane operacje i rzeczywisty czas wykonania. Wierszy pozycji zamówienia nie można edytować, dodawać, usuwać ani kopiować/wklejać. Numer PO jest przechowywany z zamówieniem. Aplikacja porównuje czas rzeczywisty z sumą zaplanowanych godzin operacji danego itemu pomnożoną przez ilość: zielony wynik oznacza czas nieprzekraczający planu, a czerwony — przekroczenie. Zmiany zapisuje przycisk **Save Order**.
- **Settings > Stats** otwiera raport wszystkich zamówień z podsumowaniem liczby statusów, wartości subtotal, rabatu, netto, VAT i brutto oraz rozbiciem finansowym każdego zamówienia.
- W **Settings** administrator może przez przycisk **Admin** i PIN ustawić **Software End Date** oraz godzinę końcową w formacie HH:MM (zegar 24-godzinny). Po upływie tego terminu aplikacja przechodzi w tryb tylko do odczytu: blokuje tworzenie, edycję, kopiowanie, wklejanie i usuwanie wycen/zamówień, konwersje, zmiany w bazach klientów i dostawców oraz zapisy ustawień. Blokowane jest również generowanie dokumentów, które zmieniałyby dane zamówienia (delivery note i job card). Administrator nadal może zmienić lub usunąć limit przez **Settings > Admin**. Puste pole daty usuwa limit.
- Adres e-mail klienta można zapisać w szczegółach wyceny lub w bazie klientów. **Email PDF** korzysta z adresu z wyceny, a jeśli go tam nie ma, szuka go w danych wybranej osoby kontaktowej. Zawsze otwiera nową wiadomość; gdy nie ma zapisanego adresu, pole odbiorcy pozostaje puste. Gdy klient pocztowy obsługuje Windows MAPI, PDF zostanie załączony automatycznie. W przeciwnym razie aplikacja otworzy wiadomość bez załącznika i pokaże lokalną ścieżkę PDF do ręcznego dołączenia.

## Baza klientów

Dane firm i osób kontaktowych są zapisywane w `customers_data.json`. Przycisk **Customer Database** otwiera bazę klientów. Przycisk **+** otwiera formularz dodawania nowej firmy, a dwuklik w wiersz na liście otwiera formularz edycji. W formularzu edycji można również usunąć wybraną osobę kontaktową lub firmę. Przy dodawaniu firmy osoba kontaktowa jest opcjonalna; adres jest zapamiętywany dla firmy, a każda osoba kontaktowa ma osobny zapis telefonu i e-maila. Wybór zapisanej firmy i osoby automatycznie uzupełnia te dane w formularzu wyceny. Dotychczasowy format pliku klientów jest konwertowany do nowego formatu przy uruchomieniu aplikacji.

## Baza dostawców i materiały

W formularzu elementu wyceny pod tabelą operacji można podać **Required Material**, **Material Cost**, **MCT Number** i **Cast**, a także wybrać lub wpisać **Supplier**. Koszt materiału jest uwzględniany w cenie pozycji i sumie wyceny. PDF pokazuje cenę każdej pozycji, rabat oraz końcową sumę bez VAT i z VAT; nie ujawnia nazwy użytego materiału. Nowy dostawca wpisany w formularzu zostanie dopisany do bazy. Przycisk **Suppliers** na górnym pasku otwiera bazę; przycisk **+** otwiera formularz dodawania, a dwuklik wiersza — edycji. W formularzu edycji można też usunąć dostawcę. Dane bazy są przechowywane w `suppliers_data.json`.

## Logo firmy

W **Settings > Links** wybierz plik logo przez **Browse...** i zapisz ustawienia. Ścieżka jest zapamiętywana w `cnc_settings.json`. Logo będzie wyświetlane w lewym górnym rogu aplikacji; jego pozycję w każdym typie PDF można ustawić w **Settings > PDF Layout Generator**. PNG można wyświetlać bez dodatkowych bibliotek; do wyświetlania logo JPEG/JPG w aplikacji wymagany jest Pillow (`pip install Pillow`). Aby usunąć logo, wyczyść ścieżkę w ustawieniach i zapisz zmiany.

Stawki godzinowe operacji można zmienić w **Settings > Rates**. W tym oknie można też dodać nową operację, podając jej nazwę i stawkę; po zapisaniu pojawi się ona na liście procesów przy dodawaniu operacji do pozycji wyceny.

## Układ PDF

Otwórz **Settings > PDF Layout Generator**, aby osobno edytować układ oferty, delivery note i jobcard. Na podglądzie strony A4 można przeciągać pola oraz ustawiać ich pozycję, wymiary, etykietę lub tekst, krój i styl czcionki, rozmiar, kolor i widoczność. Przycisk **Preview PDF** tworzy przykładowy dokument na podstawie aktualnego układu, także przed zapisaniem zmian, i otwiera go w domyślnym czytniku PDF. Lista **Add information** pozwala dodawać dostępne dane firmy, klienta i zamówienia, podsumowania, operacje oraz własny tekst. Aby wstawić tabelę pozycji do oferty lub delivery note, wybierz **Quoted items and prices** albo **Delivery items** i naciśnij **Add items table**. Zaznacz potrzebne kolumny w sekcji **Table columns (select fields)** i wybierz **Apply table columns**; kolumny można później zmienić po zaznaczeniu tabeli na liście pól. Tabela zachowuje nagłówki po podziale między strony. Zmiany zapisuje **Save layouts**; **Reset document layout** przywraca układ domyślny wybranego dokumentu. Numery rejestracyjne są domyślnie umieszczane w stopce ofert i delivery notes, nie jobcard.

## Folder zapisu PDF

W **Settings > Links** wybierz **PDF Save Folder** przyciskiem **Browse...** i zapisz zmiany. Wszystkie generowane PDF-y, również załączniki przygotowywane do e-maila, będą zapisywane w wybranym folderze. Puste pole zachowuje dotychczasowe zachowanie i zapisuje plik w bieżącym folderze uruchomienia aplikacji.

Jeśli brakuje biblioteki PDF:

```bash
pip install fpdf2
```
