from elasticsearch import Elasticsearch
from elasticsearch.helpers import scan
from .collections import ItemCollection
import sys


def reindex(from_index, to_index):
    es_current = Elasticsearch(host='localhost', port=9200, 
          http_auth=None)

    es_target = Elasticsearch(host='localhost', 
        port=9200, http_auth=None)

    query = { "query" : { "match_all" : {} }}
    all_docs = scan(client = es_current, query = query, scroll= "5m", 
        index = from_index, doc_type = ItemCollection.doc_type)

    items = ItemCollection(es_target, index=to_index)
    for a in all_docs:
        item = items.make_model(a['_source'])
        item._index(id=a['_id'], body=item.data)



def create_index(index_name):
    es = Elasticsearch(host='localhost', port=9200, 
          http_auth=None)

    es.indices.create(index_name, ignore=400)
    es.indices.put_mapping(doc_type=ItemCollection.doc_type, 
        body=ItemCollection.mapping, index=index_name)


def update_aliases(from_index, to_index):
    es = Elasticsearch(host='localhost', port=9200, 
          http_auth=None)

    es.indices.delete_alias(index=from_index, name='item_alias', ignore=[400,404])
    es.indices.put_alias(index=to_index, name='item_alias', ignore=[400,404])


def delete_index(index_name):
    es = Elasticsearch(host='localhost', port=9200, 
          http_auth=None)

    es.indices.delete(index=index_name, ignore=[400,404])


def migrate_index(from_index, to_index):
    create_index(to_index)
    reindex(from_index, to_index)
    update_aliases(from_index, to_index)
    delete_index(from_index)


if __name__ == "__main__":
    args = sys.argv

    if args[1] == 'reindex':
        reindex(args[2], args[3])

    if args[1] == 'migrate':
        migrate_index(args[2], args[3])