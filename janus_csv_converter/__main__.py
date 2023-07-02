#!/usr/bin/env python3
import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import cchardet
import logging


# HomeBank CSV column format:
# 0 Date (y-m-d, d-m-y or -m-d-y)
# 1 Payment type (see below)
# 2 Info
# 3 Payee
# 4 Memo
# 5 Amount
# 6 Category
# 7 Tags

# HomeBank Payment codes:
# 1 Credit card - tarjeta de crédito
# 2 Check - Cheque
# 3 Cash - Efectivo
# 4 Transfer - Transferencia
# 5 UNUSED
# 6 Debit card - Tarjeta de débito
# 7 Standing order - orden de pago
# 8 Electronic payment - pago electrónico
# 9 Deposit - Deposito
# 10 Financial Institution Fee
# 11 Direct debit


class AMAZONVISA(csv.Dialect):
    delimiter = ';'
    quotechar = '\"'
    doublequote = True
    skipinitialspace = False
    lineterminator = '\r\n'
    quoting = csv.QUOTE_MINIMAL


class DKB(csv.Dialect):
    delimiter = ';'
    quotechar = '\"'
    doublequote = True
    skipinitialspace = False
    lineterminator = '\r\n'
    quoting = csv.QUOTE_MINIMAL


class N26(csv.Dialect):
    delimiter = ','
    quotechar = '\"'
    doublequote = True
    skipinitialspace = False
    lineterminator = '\r\n'
    quoting = csv.QUOTE_MINIMAL


class PAYPAL(csv.Dialect):
    delimiter = ','  # Was ';' until October 2022
    quotechar = '\"'
    doublequote = True
    skipinitialspace = False
    lineterminator = '\r\n'
    quoting = csv.QUOTE_MINIMAL


class SANTANDERPL(csv.Dialect):
    delimiter = ';'
    quotechar = '\"'
    doublequote = True
    skipinitialspace = False
    lineterminator = '\r\n'
    quoting = csv.QUOTE_MINIMAL


class SPENDEE(csv.Dialect):
    delimiter = ','  # Was ',' until October 2022
    quotechar = '\"'
    doublequote = True
    skipinitialspace = False
    lineterminator = '\n'
    quoting = csv.QUOTE_MINIMAL


class AMEX(csv.Dialect):
    delimiter = ';'
    quotechar = '\"'
    doublequote = True  # I am so tired of this...
    skipinitialspace = False
    lineterminator = '\r\n'
    quoting = csv.QUOTE_MINIMAL


def post_process(transaction):  # TODO externalize all hardcoced strings
    if "paypal" in transaction[3].casefold():  # Payee
        person_split = transaction[4].split()
        if len(person_split) == 0:
            return
        if person_split[len(person_split) - 1] == "bei":
            transaction[3] = "PayPal"
        else:
            payee_split = transaction[3].split()
            transaction[3] = "PAYPAL"
            transaction[4] = payee_split[1] + " " + transaction[4]
        transaction[7] += "paypal"  # Tagging paypal


def amex_parser(csvfile):
    """
    American Express CSV format (Germany)
    """
    transactions = csv.DictReader(csvfile, dialect=AMEX)
    out = []
    row: dict
    for row in transactions:
        # This is so wrong in son many levels.
        # WHAT THE FUCK IS WRONG WITH AMEX?
        # CSV, MOTHERFUCKER, DO YOU SPEAK  IT???

        # Date
        date = datetime.strptime(row['Datum'], "%d/%m/%Y").strftime('%Y-%m-%d')

        # Payment type, that one is easy...
        payment = 1

        # Memo
        # Constructing as "Memo-Adress-Statd,Land
        address = re.sub(r"\n", ", ", row['Adresse'])  # Removing those pesky line breaks
        memo = f"{row['Beschreibung']}-{row['Weitere Details']}-{row['Adresse']}, {row['PLZ']}, {row['Land']}"

        # Postprocessing of the Memo field
        # AMEX GET YOUR SHIT TOGETHER
        memo = re.sub(r"\s{2,}", " ", memo)  # Get rid of all extra spaces
        memo = re.sub(r"\n", ", ", memo)  # Remove extra line breaks (LF characters)
        memo = re.sub(r"--", '-', memo)  # Remove double dash in case of empty additional details

        # Payeel leaving it empty as always
        payee = ''

        # Amount as float, and make negative
        amount = float(row['Betrag'].replace(',', '.'))
        amount *= -1

        info = row.get('Karteninhaber', '')
        category = tags = ''

        out_row = [date, payment, info, payee, memo, amount, category, tags]
        post_process(out_row)
        out.append(out_row)
    return out


def dkb_visa_parser(csvfile):
    dkb_visa_fields = ["saldo",  # 0 Umsatz abgerechnet und nicht im Saldo enthalten
                            "wertstellung",  # 1 Efective date?
                            "Belegdatum",  # Day of the operation?
                            "Beschreibung",  # 3 Memo
                            "Betrag",  # 4 Betrag amount
                            "Ubetrag"]  # 5 Non euro amount

    # Ignore header without useful data
    lines = csvfile.readlines()
    i = 1
    for line in lines:
        # simple heuristic to find the csv header line. Both these strings
        # appear in headers of the cash and visa CSVs.
        if "Betrag" in line and "Wertstellung" in line:
            trimmedfile = lines[i:]
            break
        i += 1

    transactions = csv.DictReader(trimmedfile, fieldnames=dkb_visa_fields, dialect=DKB)
    out = []
    for row in transactions:
        tags = ''

        # Date
        date = datetime.strptime(row['Belegdatum'], "%d.%m.%Y").strftime('%Y-%m-%d')

        # Payment type, that one is easy...
        payment = 1

        # Payee
        payee = ''

        # Info and memo
        info = ''
        memo = row['Beschreibung']

        # Amount
        amount = row['Betrag']

        if row['Ubetrag'] != '':
            split_ubetrag = row['Ubetrag'].split()
            currency_type = split_ubetrag[1]
            tags += " " + currency_type
            memo += " - " + currency_type + split_ubetrag[0]

        category = ''

        out_row = [date, payment, info, payee, memo, amount, category, tags]
        out.append(out_row)
    return out


def dkb_parser(csvfile):
    """
    DKB CSV Format
    "buchungstag"
    "wertstellung",
    "buchungstext",
    "beguenstigter",
    "verwendungszweck",
    "kontonummer",
    "blz",
    "betrag",
    "glaeubigerID",
    "mandatsreferenz",
    "kundenreferenz"]
    """

    dkb_fields = ["buchungstag",  # 0 Date
                   "wertstellung",  # 1 Efective date?
                   "buchungstext",  # 2 Memo? Payment?
                   "beguenstigter",  # 3 Payee
                   "verwendungszweck",  # 4 Memo
                   "kontonummer",  # 5 Account number
                   "blz",  # 6
                   "betrag",  # 7 Amount
                   "glaeubigerID",  # 8 transaction ID?
                   "mandatsreferenz",  # 9 transaction ID?
                   "kundenreferenz"]  # 10 transaction ID?

    # Ignore header without useful data
    lines = csvfile.readlines()
    i = 1
    for line in lines:
        # simple heuristic to find the csv header line. Both these strings
        # appear in headers of the cash and visa CSVs.
        if "Betrag" in line and "Wertstellung" in line:
            trimmedfile = lines[i:]
            break
        i += 1

    transactions = csv.DictReader(trimmedfile, fieldnames=dkb_fields, dialect=DKB)
    out = []
    for row in transactions:

        # Date
        date = datetime.strptime(row['wertstellung'], "%d.%m.%Y").strftime('%Y-%m-%d')

        # Decode payment
        payment_list = {
            "folgelastschrift": 8,  # OLD, possible deprecated Electronic payment
            "gutschrift": 4,  # Bank transfer
            "lastschrift": 8,  # Electronic payment
            "umbuchung": 4,  # Transfer between acounts
            "dauerauftrag": 7,  # Standing order
            "abschluss": 10,  # Deposit
            "kartenzahlung/-abrechnung": 6,  # Debit card
            "kartenzahlung": 6,  # Debit Card
            "gutschr. ueberweisung": 4,  # Transfer, probably between DKB accounts
            "online-zahlung": 8,  # Electronic payment
            "bargeldabhebung": 3,  # Cash, that means Geldoautomat
            "online-ueberweisung": 4,  # Online transfer
            "überweisung": 4,  # Bank transfer
        }
        payment = payment_list.get(str(row['buchungstext']).casefold(), 0)

        # Payee
        payee = ''

        # Memo
        memo = f"{row['beguenstigter']}-{row['verwendungszweck']}-{row['kontonummer']}"

        # Amount
        amount = row['betrag']

        # Info, category and tags
        info = category = tags = ''

        out_row = [date, payment, info, payee, memo, amount, category, tags]
        post_process(out_row)
        out.append(out_row)
    return out


def amazon_visa_parser(csvfile):
    """
    Amazon CSV Format (German)
    0 Kreditkartennummer - Credit card number
    1 Transaktionsdatum - Transaction date
    2 Buchungsdatum - Effective date
    3 Händler (Name, Stadt & Land) - Merchant (name, city & country)
    4 Umsatzkategorie - Sales category
    5 Betrag in Fremdwährung - Amount in foreign currency
    6 Einheit Fremdwährung - Unit foreign current
    7 Umrechnungskurs - Exchange rate
    8 Betrag in Euro - Amount in Euros
    9 Amazon Punkte - Amazon points
    10 Prime Punkte - Prime points
    """

    # Ignore header without useful data
    lines = csvfile.readlines()
    i = 1
    for line in lines:
        if "Kreditkartennummer" in line and "Transaktionsdatum" in line:
            trimmedfile = lines[i:]
            break
        i += 1

    transactions = csv.reader(trimmedfile, dialect=AMAZONVISA)
    out = []
    for row in transactions:
        # If row shows "points" exchange, ignore
        if row[0] == "" and row[8] == "":
            continue
        # Date
        date = datetime.strptime(row[1], "%d.%m.%Y").strftime('%Y-%m-%d')

        # Memo
        memo = f"{row[3]}-{row[4]}"
        # Payee
        payee = ''
        # Payment
        payment = 1  # Credit card, fixed for this account type
        # Amount
        amount = float(row[8].replace(',', '.'))
        amount *= -1

        # Info, category and tags
        info = category = tags = ''

        # International currency
        if row[6] != "EUR" and row[5] != "":
            info = "Original Price = " + row[5] + " " + row[6] + " - " + row[7] + " exchange rate"

        out_row = [date, payment, info, payee, memo, amount, category, tags]
        post_process(out_row)
        out.append(out_row)
    return out


def paypal_parser(csvfile):
    """
    PayPal CSV Format (English - German)
    English needed, read as dictionary
    """

    type_general_currency_conversion = "General Currency Conversion"
    type_general_credit_deposit = "General Credit Card Deposit"
    type_general_authorization = "General Authorization"
    transactions = csv.DictReader(csvfile, dialect=PAYPAL)

    out = []
    for row in transactions:
        # In case of "General Authorization", ignore the transaction and continue
        if row['Type'] == type_general_authorization:
            continue

        # Date
        if '\t' in row['Date']:  # Because PayPal for some reason adds an empty line with a tab at EOF
            continue
        date = datetime.strptime(row['Date'], "%d/%m/%Y").strftime('%Y-%m-%d')

        # Payment
        payment = 8

        # Info
        memo = row['Subject'] + " " + row['Note']
        memo += " - " + row['Transaction ID']

        # Amount
        amount = float(row['Net'].replace(',', '.'))
        if row['Currency'] != 'EUR':
            memo += " " + row['Currency'] + "=" + str(amount)

        # Payee
        payee = row['Name'] + ' - ' + row['To Email Address']

        # Info, category and tags
        info = category = tags = ''

        # Check if it is foreign currency
        if row['Type'] == type_general_currency_conversion:
            if row['Currency'] != 'EUR':
                continue
            transaction_id = row['Reference Txn ID']
            for i in out:
                if transaction_id in i[4]:  # If the transaction IDs match
                    i[5] = amount
                    break
            continue

        out_row = [date, payment, info, payee, memo, amount, category, tags]
        out.append(out_row)
    return out


def santander_pl_parser(csvfile):
    """
    Santander Bank Polska CSV format:
    0 Effective Date
    1 Date of operation
    2 Title of operation
    3 Payee details
    4 Payee bank account number
    5 Amount (PLN)
    6 Saldo after
    """

    transactions = csv.reader(csvfile, dialect=SANTANDERPL)
    next(transactions)  # Skipping the first line with Metadata

    out = []
    for row in transactions:
        # Date
        date = datetime.strptime(row[1], "%d-%m-%Y").strftime('%Y-%m-%d')
        # Memo
        memo = row[2] + " - " + row[4]
        # Payee
        payee = row[3]
        # Amount
        amount = float(row[5].replace(',', '.'))
        # Payment type
        if amount > 0:
            payment = 9
        else:
            payment = 8

        # Info, category, tags
        info = category = tags = ''
        tags = ''
        out_row = [date, payment, info, payee, memo, amount, category, tags]

        post_process(out_row)
        out.append(out_row)
    return out


def spendee_parser(csvfile):
    """
    Spendee app CSV format:
    0 Date
    1 Wallet
    2 Category name
    3 Amount
    4 Currency
    5 Note
    6 Labels
    7 Author
    """

    transactions = csv.DictReader(csvfile, dialect=SPENDEE)
    out = []
    for row in transactions:
        # Date
        dateiso = datetime.fromisoformat(row['Date'])
        date = dateiso.strftime('%Y-%m-%d')
        # Payment
        payment = 3
        # Memo
        memo = row['Note']
        memo = memo.replace("\n", '')  # Remove innecesary new lines in the middle of note
        memo = memo.replace("\r", '')
        memo += " - " + row['Category name']
        memo += " - " + row['Labels']

        # Payee
        payee = ''
        # Info
        info = ''
        # Amount
        amount = float(row['Amount'])
        # Category & tags
        category = ''
        tags = ''

        out_row = [date, payment, info, payee, memo, amount, category, tags]
        post_process(out_row)
        out.append(out_row)
    return out


def n26_parser(csvfile):
    """
    N26 CSV Format (Spanish)
    0 Fecha
    1 Beneficiario
    2 Número de cuenta
    3 Tipo de transacción
    4 Referencia de pago
    5 Categoría
    6 Cantidad (EUR)
    7 Cantidad (Divisa extranjera)
    8 Tipo de divisa extranjera
    9 Tipo de cambio
    """

    transactions = csv.DictReader(csvfile, dialect=N26)
    out = []

    for row in transactions:
        date = row['Fecha']
        payee = row['Beneficiario']
        memo = f"{row['Beneficiario']}-{row['Referencia de pago']}"
        # Decode payment
        payment_list = {
            "Pago con MasterCard": 6,  # Debit card
            "Transferencia saliente": 4,  # Transferencia
            "Domiciliación bancaria": 8,  # Pago electrónico
            "Ingreso": 9,  # Depósito
        }
        payment = payment_list.get(row['Tipo de transacción'], 0)
        amount = row['Cantidad (EUR)']

        category = ''
        tags = ''
        info = ''

        # International currency
        if row['Tipo de divisa extranjera'] != "EUR" and row['Tipo de divisa extranjera'] != "":
            info = "Original Price = " + row['Cantidad (Divisa extranjera)'] + " " + row[
                'Tipo de divisa extranjera'] + " - " + row['Tipo de cambio'] + " exchange rate"
        out_row = [date, payment, info, payee, memo, amount, category, tags]
        out.append(out_row)
    return out


def load_parse_csv_file(path, banktype):
    # Trying to detect file encoding!
    file_path = Path(path)
    logging.debug(f"Path input file = {file_path}")
    file_bytes = file_path.read_bytes()
    detection = cchardet.detect(file_bytes)
    encoding = detection["encoding"]
    confidence = detection["confidence"]
    logging.debug(f"File encoding= {encoding} - witch confidence= {confidence}")
    if confidence < 0.75:
        logging.warning("Confidence on the encoding type is too low, output file may contain errors!")

    with open(file_path, encoding=encoding) as csvfile:
        if args.n26:  # N26
            parsed_data = n26_parser(csvfile)
            bank = 'N26'
        elif args.dkb:
            parsed_data = dkb_parser(csvfile)
            bank = 'DKB'
        elif args.dkbvisa:
            parsed_data = dkb_visa_parser(csvfile)
            bank = 'DKBVISA'
        elif args.amazonvisa:
            parsed_data = amazon_visa_parser(csvfile)
            bank = 'AMAZONVISA'
        elif args.paypal:
            parsed_data = paypal_parser(csvfile)
            bank = 'PAYPAL'
        elif args.santanderPL:
            parsed_data = santander_pl_parser(csvfile)
            bank = 'SANTANDER-PL'
        elif args.spendee:
            parsed_data = spendee_parser(csvfile)
            bank = 'SPENDEE'
        elif args.amex:
            parsed_data = amex_parser(csvfile)
            bank = 'AMEX'
        else:
            raise ValueError("No valid CSV bank format was selected")
        return parsed_data, bank


def argument_parser():
    parser = argparse.ArgumentParser(description=f"Converta a CSV file exported from several banks and credit cards providers to \
                                     a HomeBank compatible format.")
    parser.add_argument("filename", help="Input CSV file to be converted")
    parser.add_argument('-o', '--output-file', default="HomeBank_{bank}_{date}.csv",
                        help="Name (and optionally, path) of the output file")
    parser.add_argument('--debug', '-d', action="store_true", help="Show debugging log traces")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--n26', action="store_true", help="convert a N26 CSV file (with headers in Spanish)")
    group.add_argument('--dkb', action="store_true", help="convert a DKB Cash (Germany) CSV file")
    group.add_argument('--dkbvisa', action="store_true", help="convert a DKB VISA (Germany) CSV file")
    group.add_argument('--amazonvisa', action="store_true", help="convert a Amazon VISA (Germany) CSV file")
    group.add_argument('--paypal', action="store_true",
                       help="convert from PayPal CSV file (Completed Payments) with Default fields (merchant view)")
    group.add_argument('--santanderPL', action="store_true", help="convert from Santander Bank Polska CSV file")
    group.add_argument('--spendee', action="store_true", help="convert from Spendee app CSV file")
    group.add_argument('--amex', action="store_true",
                       help="convert from American Express (Germany) CSV file (exported with all values/details)")
    return parser.parse_args()


def main():
    global args
    args = argument_parser()
    input_path = args.filename

    if args.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    log_format = '[%(asctime)s] %(levelname)s %(lineno)d - %(funcName)s(): %(message)s'
    logging.basicConfig(stream=sys.stdout, format=log_format, level=log_level)
    logging.debug("Starting program...")

    # Parsing and categorizing the data
    parsed_data, bank = load_parse_csv_file(input_path, args)
    # Writing in an output
    today = datetime.today()
    output_path = args.output_file.format(date=today.strftime("%Y%m%d"), bank=bank)
    with open(output_path, 'w', newline='', encoding="utf-8") as csvfile:
        csvwriter = csv.writer(csvfile, delimiter=';', quotechar='\"', quoting=csv.QUOTE_MINIMAL)
        for row in parsed_data:
            csvwriter.writerow(row)


if __name__ == '__main__':
    main()
