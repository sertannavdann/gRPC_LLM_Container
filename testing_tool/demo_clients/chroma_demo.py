import grpc
import sys
sys.path.insert(0, '..')
from chroma_service import chroma_pb2, chroma_pb2_grpc
from google.protobuf import struct_pb2


def run():
    channel = grpc.insecure_channel('localhost:50052')
    stub = chroma_pb2_grpc.ChromaServiceStub(channel)
    # Add a document with non-empty metadata (Chroma requires metadata map)
    meta = struct_pb2.Struct()
    meta.update({"source": "demo", "topic": "coffee"})
    doc = chroma_pb2.Document(id='demo-1', text='This is a demo document about coffee and AI.', metadata=meta)
    add_resp = stub.AddDocument(chroma_pb2.AddDocumentRequest(document=doc))
    print('AddDocument success:', add_resp.success)
    # Query
    query_resp = stub.Query(chroma_pb2.QueryRequest(query_text='coffee', top_k=3))
    print('Query results count:', len(query_resp.results))
    for r in query_resp.results:
        # Some older proto generations may not include an 'id' field on results; handle gracefully
        rid = getattr(r, 'id', '<no-id>') if r is not None else '<no-id>'
        print('-', rid, r.text[:200])

if __name__ == '__main__':
    run()
