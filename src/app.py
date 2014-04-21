import logging
import time
import sys
import json
import importlib
import os.path, pkgutil
import suckas

from datetime import datetime
from qr import Queue
from config import settings
from cn_store_py.connect import get_connection
from bson import objectid

logger = logging.getLogger(__name__)

db = get_connection()

app_queue = Queue(settings.QUEUE_NAME, host=settings.REDIS_HOST, 
            port=settings.REDIS_PORT, password=settings.REDIS_PASSWORD)
transform_queue = Queue(settings.TRANSFORM_QUEUE_NAME, host=settings.REDIS_HOST, 
            port=settings.REDIS_PORT, password=settings.REDIS_PASSWORD)

app_queue.serializer = json
transform_queue.serializer = json

pkgpath = os.path.dirname(suckas.__file__)
sucka_names = [name for _, name, _ in pkgutil.iter_modules([pkgpath])]


def setup_sources(sucka_names):
    modules = [importlib.import_module('suckas.'+name) for name in sucka_names]

    def upsert_source(mod):
        definition = mod.definition
        return db.Source.find_and_modify(
            { 'internalID': definition['internalID'] },
            { '$set': definition },
            { 'upsert': True, 'new': True }
        )

    return [upsert_source(mod) for mod in modules if hasattr(mod, 'definition')]


def get_sucka_for_source(source):
    source_type = source['sourceType']
    if source_type not in sucka_names:
        return None

    return importlib.import_module('suckas.'+source_type)


def post_suck(source, last_retrieved=None):
    source['lastRun'] = datetime.now()
    source['hasRun'] = True

    if last_retrieved:
        del last_retrieved['_id']
        source['lastRetrieved'] = json.loads(last_retrieved.to_json())

    source.save()
    return source


def save_item(data):
    item = db.Item.find_and_modify(
        { 'remoteID': data['remoteID'], 'source': data['source'] },
        { '$set': data },
        { 'upsert': True, 'new': True }
    )

    if not item:
        item = db.Item.one({ 'remoteID': data['remoteID'], 'source': data['source'] })

    id_str = str(item['_id'])
    logger.info("Pushing task "+id_str)
    transform_queue.push(json.dumps({'id': id_str}))
    return item


def handle_broken_source(source, data, error):
    source.status = 'failing'
    source.failData = data
    source.save()


def do_suck(source):
    sucka = get_sucka_for_source(source)

    if not sucka:
        logger.warn('no sucka found for ' + source['sourceType'])
        return False

    last_retrieved = sucka.suck(save_item, handle_broken_source)
    return post_suck(source, last_retrieved)
        

def start_app():
    setup_sources(sucka_names)

    while True:
        try:
            task = app_queue.pop()
            if task:
                try:
                    data = json.loads(task)
                    task = None
                    source = db.Source.one({'_id': objectid.ObjectId(data['id'])})
                    if source:
                        do_suck(source)
                except Exception, e:
                    import traceback
                    logger.error("Problem! " + str(e))
                    logger.error(traceback.format_exc())
            time.sleep(1)
        except KeyboardInterrupt:
            logger.warn("Exiting suckapy")
            sys.exit()


if __name__ == "__main__":
    args = sys.argv

    if len(args) > 1 and args[1] == '--source':
        source = db.Source.one({'_id': objectid.ObjectId(args[2])})
        if source:
            logger.info("Sucking for source "+source['sourceType'])
            do_suck(source)
    else:
        logger.warn("Starting suckapy")
        start_app()