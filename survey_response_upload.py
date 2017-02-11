"""
Python code to upload CSV survey data to Open Humans project member accounts.

Pre-reqs:
  - open_humans_api https://github.com/OpenHumans/open-humans-api/
  - your survey data is CSV format, with header row describing survey questions
  - one of the columns is the Open Humans Project Member ID (8 digits)
"""
# Standard library modules.
import csv
import logging
import json
import re

# Third party modules.
import click  # For commandline options, installed as prereq of open-humans-api
import ohapi  # from open-humans-api
import requests  # For HTTP methods, installed as prereq of open-humans-api

# Python 2/3 compatibility.
try:
    input = raw_input  # Rename Python 2 version to Python 3.
except NameError:
    pass

# Set up logging.
logging.basicConfig(level=logging.INFO)

# Regular expression matching project member ID.
RE_ID = '^[0-9]{8}$'

# Defaults for uploaded data files.
UPLOAD_FILENAME = 'survey-data.json'
DEFAULT_DESCRIPTION = 'Project survey data.'
DEFAULT_TAGS = 'json survey'


def get_projmemid_fieldname(surveydata):
    """Determine which CSV column has project member IDs."""
    # Use the first row of data to guess the ID column. Ask user to confirm.
    with open(surveydata) as f:
        reader = csv.DictReader(f)
        firstrow = next(reader)
        id_fieldname = None
        for fieldname in reader.fieldnames:
            if re.match(RE_ID, firstrow[fieldname]):
                idx = reader.fieldnames.index(fieldname) + 1
                prompt = 'Is project member ID column {}? ({}) (Y/N): '.format(
                    idx, fieldname)
                response = input(prompt)
                if response.upper() in ['Y', 'YES']:
                    id_fieldname = fieldname
                    break

    # Return fieldname if we've got one, otherwise raise an error.
    if id_fieldname:
        return id_fieldname
    else:
        raise Exception('Unable to determine column with project member ID.')


def load_survey_data(surveydata):
    """Load survey data into a dict from the CSV file."""
    # Check that there's a header.
    with open(surveydata) as f:
        if not csv.Sniffer().has_header(f.read(1024)):
            raise Exception("CSV data doesn't appear to have a header!")

    # Get the CSV column fieldname for project member ID.
    id_fieldname = get_projmemid_fieldname(surveydata)

    # Load data into a dict.
    loaded_data = {}
    row_count = 0
    with open(surveydata) as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_count += 1
            # Save responses in dict, using project member ID as lookup key.
            if re.match(RE_ID, row[id_fieldname]):
                loaded_data[row[id_fieldname]] = row
            else:
                raise Exception('Row {} appears to have malformed '
                                'project member ID!'.format(row))
    return loaded_data


@click.command()
@click.option('--mastertoken', required=True, help='Project master access token')
@click.option('--surveydata', required=True, help='Path to survey data CSV file')
@click.option('--filename', default=UPLOAD_FILENAME,
              help='Name for uploaded file. (Default: "{}")'.format(
                  UPLOAD_FILENAME))
@click.option('--description', default=DEFAULT_DESCRIPTION,
              help='File description. (Default: "{}")'.format(
                  DEFAULT_DESCRIPTION))
@click.option('--tags', default=DEFAULT_TAGS, help='String with '
              'space-separated tags for file. (Default: "{}")'.format(
                  DEFAULT_TAGS))
def surv_upload(mastertoken, surveydata, filename=UPLOAD_FILENAME,
                description=DEFAULT_DESCRIPTION, tags=DEFAULT_TAGS):
    """
    Upload survey data from CSV file to project member accounts.

    Notes:

      - Data is uploaded in JSON format, with the filename 'survey-data.json'

      - If more than one row contains responses for a given member, only the
        last response is uploaded.

      - If a 'survey-data.json' file already exists, it's removed and replaced.
    """
    # Load survey data from CSV file.
    loaded_data = load_survey_data(surveydata=surveydata)

    # Use ohapi to get current project data. (We can use this to learn if
    # there's a pre-existing file that we'll be deleting and overwriting.)
    proj = ohapi.OHProject(master_access_token=mastertoken)

    # Upload data as JSON-format files to each project member's OH account.
    for projmemid in loaded_data:

        # Output warning and skip if this project member ID doesn't seem valid.
        try:
            member_data = proj.project_data[projmemid]
        except KeyError:
            logging.info("Skipping '{}', invalid member ID.".format(projmemid))
            continue

        # The API lists all files accessible to the project - from other
        # sources as well as the project itself. To get just the project's
        # files, a list is generated excluding files from shared data sources.
        curr_project_data = {f['basename']: f for f in member_data['data'] if
                             f['source'] not in member_data['sources_shared']}

        # Delete current file(s) by this name, if it exists.
        if filename in curr_project_data:
            logging.info('Deleting current {} for {}'.format(
                filename, projmemid))
            del_url = (
                'https://www.openhumans.org/api/direct-sharing/project/files'
                '/delete/?access_token={}'.format(proj.master_access_token))
            requests.post(del_url, data={'project_member_id': projmemid,
                                         'file_basename': filename})

        # Upload survey data as JSON string.
        logging.info('Uploading {} for {}'.format(filename, projmemid))
        up_url = ('https://www.openhumans.org/api/direct-sharing/project/files/'
                  'upload/?access_token={}'.format(proj.master_access_token))
        metadata = {
            "tags": tags.split(' '),
            "description": description,
        }
        r = requests.post(up_url,
                          files={'data_file': (
                                 filename,
                                 json.dumps(loaded_data[projmemid]))},
                          data={'project_member_id': projmemid,
                                'metadata': json.dumps(metadata)})

        # Report success/failure.
        if r.status_code == 201:
            logging.info('Upload of {} for {} complete.'.format(
                filename, projmemid))
        else:
            logging.warning('Upload error of {} for {}!'.format(
                filename, projmemid))


# The following runs when a script is called on the commandline.
if __name__ == '__main__':
    surv_upload()
