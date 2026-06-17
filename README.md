# data.public.lu - Peppol mapping

The goal of this project is to map all public sector organisations on data.public.lu with their respective Peppol ID.

The main source file for this mapping is the CSV file named [datapublic-peppol-mapping-source.csv](./datapublic-peppol-mapping-source.csv). If you find any mistake in this file, please send us a pull request.

In the source file, there are four types of relationships for the mapping between an organisation and a Peppol ID:
- same
- subset: the data.public.lu organisation is part of the organisation corresponding to the Peppol ID
- superset: the organisation corresponding to the Peppol ID is part of the data.public.lu organisation
- group: the organisation on data.public.lu corresponds to two or more Peppol IDs.

The "superset" and "group" relationships do not enable to find a data.public.lu organization by its Peppol ID. These relationships are filtered out in the released files.

## Releases

You can find the data from this project converted in various output formats in the [releases section](https://github.com/opendatalu/datapublic-peppol-mapping/releases/tag/latest) of this project.

We have added one file to this release named organizations-without-peppol-id.csv which contains the list of organisations on data.public.lu which are not yet part of this mapping.

Two further files report inconsistencies found between the source file and the reference APIs (an `issue_source` column tells whether the problem comes from `data.public.lu` or from `Peppol`):
- unknown-ids.csv: source rows whose data.public.lu or Peppol ID is not found in the corresponding API.
- name-mismatches.csv: source rows whose data.public.lu or Peppol name differs from the one returned by the corresponding API.

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