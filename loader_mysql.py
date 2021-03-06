#!/usr/bin/python
#  -*- coding: utf-8 -*-
""" Loader for Taiwan government e-procurement website"""

import os
import logging
import mysql.connector
import extractor_awarded as eta
import extractor_declaration as etd
from datetime import datetime, date
from mysql.connector import errorcode
from optparse import OptionParser
from joblib import Parallel, delayed

__author__ = "Yu-chun Huang"
__version__ = "1.0.0b"

logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

trantab = str.maketrans(
    {'\'': '\\\'',
     '\"': '\\\"',
     '\b': '\\b',
     '\n': '\\n',
     '\r': '\\r',
     '\t': '\\t',
     '\\': '\\\\',})


def gen_insert_sql(table, data_dict):
    sql_template = u'INSERT INTO {} ({}) VALUES ({}) ON DUPLICATE KEY UPDATE {}'
    columns = ''
    values = ''
    dup_update = ''

    for k, v in data_dict.items():
        if v is not None:
            if values != '':
                columns += ','
                values += ','
                dup_update += ','

            columns += k

            if isinstance(v, str):
                vstr = '\'' + v.translate(trantab) + '\''
            elif isinstance(v, bool):
                vstr = '1' if v else '0'
            elif isinstance(v, datetime) or isinstance(v, date):
                vstr = '\'' + str(v) + '\''
            else:
                vstr = str(v)

            values += vstr
            dup_update += k + '=' + vstr

    sql_str = sql_template.format(table, columns, values, dup_update)
    logger.debug(sql_str)
    return sql_str


def load_declaration(cnx_info, file_name):
    primary_key, root_element = etd.init(file_name)
    if root_element is None or primary_key is None or primary_key == '':
        logger.error('Fail to extract data from file: ' + file_name)
        return

    logger.info('Updating database (primaryKey: {})'.format(primary_key))

    try:
        cnx = mysql.connector.connect(**cnx_info)
        cnx.autocommit = False
        cur = cnx.cursor(buffered=True)

        data = etd.get_organization_info_dic(root_element)
        data.update(etd.get_procurement_info_dic(root_element))
        data.update(etd.get_declaration_info_dic(root_element))
        data.update(etd.get_attend_info_dic(root_element))
        data.update(etd.get_other_info_dic(root_element))
        data['primary_key'] = primary_key

        cur.execute('SET NAMES utf8mb4')
        cur.execute(gen_insert_sql('tender_declaration_info', data))
        cnx.commit()
    except mysql.connector.Error as e:
        if e.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            logger.error("Something is wrong with your user name or password.")
        elif e.errno == errorcode.ER_BAD_DB_ERROR:
            logger.error("Database does not exist.")
        else:
            outstr = 'Fail to update database (primary_key: {})\n\t{}'.format(primary_key, e)
            logger.warn(outstr)
            with open('load.err', 'a', encoding='utf-8') as err_file:
                err_file.write(outstr)
    except AttributeError as e:
        outstr = 'Corrupted content. Update skipped (primary_key: {})\n\t{}'.format(primary_key, e)
        logger.warn(outstr)
        with open('load.err', 'a', encoding='utf-8') as err_file:
            err_file.write(outstr)
    else:
        cnx.close()


def load_awarded(cnx_info, file_name):
    pk_atm_main, tender_case_no, root_element = eta.init(file_name)
    if root_element is None \
            or pk_atm_main is None or tender_case_no is None \
            or pk_atm_main == '' or tender_case_no == '':
        logger.error('Fail to extract data from file: ' + file_name)
        return

    pk = {'pk_atm_main': pk_atm_main, 'tender_case_no': tender_case_no}
    logger.info('Updating database (pkAtmMain: {}, tenderCaseNo: {})'.format(pk_atm_main, tender_case_no))

    try:
        cnx = mysql.connector.connect(**cnx_info)
        cnx.autocommit = False
        cur = cnx.cursor(buffered=True)

        data = eta.get_organization_info_dic(root_element)
        data.update(pk)
        cur.execute(gen_insert_sql('organization_info', data))

        data = eta.get_procurement_info_dic(root_element)
        data.update(pk)
        cur.execute(gen_insert_sql('procurement_info', data))

        data = eta.get_tender_info_dic(root_element)
        for tender in data.values():
            tender.update(pk)
            cur.execute(gen_insert_sql('tender_info', tender))

        data = eta.get_tender_award_item_dic(root_element)
        for item in data.values():
            for tender in item.values():
                tender.update(pk)
                cur.execute(gen_insert_sql('tender_award_item', tender))

        data = eta.get_evaluation_committee_info_list(root_element)
        for committee in data:
            committee.update(pk)
            cur.execute(gen_insert_sql('evaluation_committee_info', committee))

        data = eta.get_award_info_dic(root_element)
        data.update(pk)

        cur.execute('SET NAMES utf8mb4')
        cur.execute(gen_insert_sql('award_info', data))
        cnx.commit()
    except mysql.connector.Error as e:
        if e.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            logger.error("Something is wrong with your user name or password.")
        elif e.errno == errorcode.ER_BAD_DB_ERROR:
            logger.error("Database does not exist.")
        else:
            outstr = 'Fail to update database (pkAtmMain: {}, tenderCaseNo: {})\n\t{}'.format(pk_atm_main,
                                                                                              tender_case_no,
                                                                                              e)
            logger.warn(outstr)
            with open('load.err', 'a', encoding='utf-8') as err_file:
                err_file.write(outstr)
    except AttributeError as e:
        outstr = 'Corrupted content. Update skipped (pkAtmMain: {}, tenderCaseNo: {})\n\t{}'.format(pk_atm_main,
                                                                                                    tender_case_no,
                                                                                                    e)
        logger.warn(outstr)
        with open('load.err', 'a', encoding='utf-8') as err_file:
            err_file.write(outstr)
    else:
        cnx.close()


def parse_args():
    p = OptionParser()
    p.add_option('-f', '--filename', action='store',
                 dest='filename', type='string', default='')
    p.add_option('-d', '--directory', action='store',
                 dest='directory', type='string', default='')
    p.add_option('-u', '--user', action='store',
                 dest='user', type='string', default='')
    p.add_option('-p', '--password', action='store',
                 dest='password', type='string', default='')
    p.add_option('-i', '--host', action='store',
                 dest='host', type='string', default='')
    p.add_option('-b', '--database', action='store',
                 dest='database', type='string', default='')
    p.add_option('-o', '--port', action='store',
                 dest='port', type='string', default='3306')
    p.add_option("-a", '--declaration', action="store_true",
                 dest='is_declaration')
    p.add_option('-l', '--parallel', action='store',
                 dest='parallel', type='int', default=1)

    return p.parse_args()


if __name__ == '__main__':
    options, remainder = parse_args()

    user = options.user.strip()
    password = options.password.strip()
    host = options.host.strip()
    port = options.port.strip()
    database = options.database.strip()
    is_declaration = options.is_declaration
    parallel = options.parallel

    if user == '' or password == '' or host == '' or port == '' or database == '':
        logger.error('Database connection information is incomplete.')
        quit()

    connection_info = {'user': user,
                 'password': password,
                 'host': host,
                 'port': port,
                 'database': database
                 }

    f = options.filename.strip()
    if f != '':
        if not os.path.isfile(f):
            logger.error('File not found: ' + f)
        else:
            if is_declaration:
                load_declaration(connection_info, f)
            else:
                load_awarded(connection_info, f)

    d = options.directory.strip()
    if d != '':
        if not os.path.isdir(d):
            logger.error('Directory not found: ' + d)
        else:
            for root, dirs, files in os.walk(d):
                if is_declaration:
                    Parallel(n_jobs=parallel)(
                        delayed(load_declaration)(connection_info, os.path.join(root, f)) for f in files)
                else:
                    Parallel(n_jobs=parallel)(
                        delayed(load_awarded)(connection_info, os.path.join(root, f)) for f in files)
