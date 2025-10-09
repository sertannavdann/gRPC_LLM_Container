import grpc
import sys
sys.path.insert(0, '..')
from tool_service import tool_pb2, tool_pb2_grpc
from google.protobuf import struct_pb2


def run():
    channel = grpc.insecure_channel('localhost:50053')
    stub = tool_pb2_grpc.ToolServiceStub(channel)
    # Call web_search tool
    params = struct_pb2.Struct()
    params.update({'query': 'latest AI news'})
    req = tool_pb2.ToolRequest(tool_name='web_search', params=params)
    resp = stub.CallTool(req)
    print('Tool success:', resp.success)
    print('Message:', resp.message)
    if resp.results:
        for r in resp.results:
            print('-', r.title, r.url)

if __name__ == '__main__':
    run()
