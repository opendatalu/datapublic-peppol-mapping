# datapublic-peppol-mapping

The goal of this project is to map all public sector organisations on data.public.lu with their respective Peppol ID.

The main source file for this mapping is the CSV file named datapublic-peppol-mapping-source.csv. If you find any mistake in this file, please send us a pull request.

## Datasources

### Data.public.lu

Data.public.lu organizations are available via its API: [data.public.lu API reference](https://data.public.lu/fr/docapi/)
It is possible to get all organizations via the following call:
https://data.public.lu/api/1/organizations/?page=1&page_size=20
The results are paginated.

### Peppol IDs
Peppol IDs are available in this dataset:
[Liste des organismes du secteur public adressables via Peppol](https://data.public.lu/fr/datasets/liste-des-organismes-du-secteur-public-adressables-via-peppol/)


## License
This software is (c) [Information and press service](https://sip.gouvernement.lu/en.html) of the luxembourgish government and licensed under the MIT license.