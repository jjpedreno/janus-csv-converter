# **Janus - A CSV file converter for HomeBank**

This scripts allows to convert CSV files exported from your bank or credit card provider, so they can be imported 
in [HomeBank](http://homebank.free.fr/en/). HomeBank is an open-source for personal accounting, budget
and finance managing.

## **Installation and usage**
After cloning the repository, you can install the package with the developer flag: `python -m pip install -e .`. This
will also create the command *janus*, which can be used all across your Python environment.

Usage:
```bash
$  janus --help
usage: janus [-h] [-o OUTPUT_FILE] [--debug] (--n26 | --dkb | --dkbvisa | --amazonvisa | --paypal | --santanderPL | --spendee | --amex) filename
                                                                                                                                                
Converta a CSV file exported from several banks and credit cards providers to a HomeBank compatible format.                                     
                                                                                                                                                
positional arguments:                                                                                                                           
  filename              Input CSV file to be converted                                                                                          
                                                                                                                                                
options:                                                                                                                                        
  -h, --help            show this help message and exit                                                                                         
  -o OUTPUT_FILE, --output-file OUTPUT_FILE                                                                                                     
                        Name (and optionally, path) of the output file                                                                          
  --debug, -d           Show debugging log traces                                                                                               
  --n26                 convert a N26 CSV file (with headers in Spanish)                                                                        
  --dkb                 convert a DKB Cash (Germany) CSV file                                                                                   
  --dkbvisa             convert a DKB VISA (Germany) CSV file                                                                                   
  --amazonvisa          convert a Amazon VISA (Germany) CSV file                                                                                
  --paypal              convert from PayPal CSV file (Completed Payments with Default fields "merchant view")                                   
  --santanderPL         convert from Santander Bank Polska CSV file                                                                             
  --spendee             convert from Spendee app CSV file                                                                                       
  --amex                convert from American Express (Germany) CSV file (exported with all values/details)
```

You need to provide an input CSV file, select the bank or credit card, and an output file (optional). The script will
then parse and generate an output CSV file that 
[can be imported by HomeBank](http://homebank.free.fr/help/use-import.html) (via *File -> Import*).

Example: `janus --dkb -o output_file.csv my_input_file.csv.` Where `my_input_file.csv` is the statements exported from the
DKB website. Omitting `-o` flag will generate the output

## **Field mapping**
Each row a CSV file contains a single transaction (in tehory), which has to be mapped to the HomeBank format, 
[defined by 8 fields](http://homebank.free.fr/help/misc-csvformat.html#txn), including [numeric values for the 
payment type](http://homebank.free.fr/help/00-lexicon.html#payment). Each bank/credit card was mapped 
differently, depending on their original bank format, with some subjectivity on my part.

### **DKB Cash**

| Field name       | HomeBank equivalent                 |
|------------------|-------------------------------------|
| buchungstag      |                                     |
| wertstellung     | **Date** (format %Y-%m-%d)          |
| buchungstext     | **Payment type** (see table below)  |
| beguenstigter    | **Payee** + "kontonummer" as suffix |
| verwendungszweck | **Memo**                            |
| kontonummer      | **Payee**                           |
| blz              |                                     |
| betrag           | **Amount**                          |
| glaeubigerID     |                                     |
| mandatsreferenz  |                                     |
| kundenreferenz   |                                     |

The field *buchungstext* is a text field that must be mapped to the payment type:

| buchungstext              | HomeBank Payment       |
|---------------------------|------------------------|
| FOLGELASTSCHRIFT          | 8 - Electronic payment |
| Gutschrift                | 9 - Deposit            |
| Lastschrift               | 8 - Electronic payment |
| Umbuchung                 | 4 - Bank transfer      |
| Dauerauftrag              | 7 - Standing order     |
| Abschluss                 | 9 - Deposit            |
| Kartenzahlung/-abrechnung | 6 - Debit card         |

### DKB Visa
Prepaid credit cards were discountinued by DKB (in favor of Visa Debit cards) on Q1/Q2 of 2022.

| Field name   | HomeBank equivalent        |
|--------------|----------------------------|
| saldo        |                            |
| wertstellung | **Date** (format %Y-%m-%d) |
| Belegdatum   |                            |
| Beschreibung | **Memo**                   |
| Betrag       | **Amount**                 |
| Ubetrag      |                            |

### N26
Field headers are assumed to be in Spanish. Although the number of fields and their meaning apply to all languages.


| Field name                   | HomeBank equivalent          |
|------------------------------|------------------------------|
| Fecha                        | **Date** (format %Y-%m-%d)   |
| Beneficiario                 | **Payee**                    |
| Tipo de transacción          | **Payment type** (see below) |
| Referencia de pago           | **Memo**                     |
| Categoría                    |                              |
| Cantidad (EUR)               | **Amount**                   |
| Cantidad (Divisa extranjera) |                              |
| Tipo de divisa extranjera    |                              |
| Tipo de cambio               |                              |

If payment is made un foreign currency (not EUR), the **Info** field will contain the original amount and the 
exchange rate.

| Tipo de transacción    | HomeBank Payment       |
|------------------------|------------------------|
| Pago con MasterCard    | 6 - Debit card         |
| Transferencia saliente | 4 - Bank transfer      |
| Domiciliación bancaria | 8 - Electronic payment |
| Ingreso                | 9 - Deposit            |

### Amazon Visa (Deutschland)

| Field name                                                     | HomeBank equivalent       |
|----------------------------------------------------------------|---------------------------|
| Kreditkartennummer                                             |                           |
| Transaktionsdatum                                              | **Date** (format %Y-%m-%d |
| Buchungsdatum                                                  |                           |
| Händler (Name, Stadt & Land) - Merchant (name, city & country) | **Payee**                 |
| Umsatzkategorie                                                | **Memo**                  |
| Betrag in Fremdwährung                                         |                           |
| Einheit Fremdwährung                                           |                           |
| Umrechnungskurs                                                |                           |
| Betrag in Euro                                                 | **Amount**                |
| Amazon Punkte                                                  |                           |
| Prime Punkte                                                   |                           |

If payment is made un foreign currency (not EUR), the **Info** field will contain the original amount and the 
exchange rate.

### PayPal

TODO: Needs documenting

### Spendee

[Spendee](https://www.spendee.com/) is an iOS/Android app for expenditure (e.g., cash) tracking.

| Field name      | HomeBank equivalent       |
|-----------------|---------------------------|
| Date            | **Date** (format %Y-%m-%d |
| Wallet          |                           |
| Category name   |                           |
| Amount          | **Amount**                |
| Currency        |                           |
| Note            | **Memo**                  |
| Labels          |                           |
| Author          |                           |


### American Express (Deutschland)

TODO: Needs documenting
