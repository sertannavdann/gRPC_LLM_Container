# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc
import warnings

import chroma_pb2 as chroma__pb2

GRPC_GENERATED_VERSION = '1.71.0'
GRPC_VERSION = grpc.__version__
_version_not_supported = False

try:
    from grpc._utilities import first_version_is_lower
    _version_not_supported = first_version_is_lower(GRPC_VERSION, GRPC_GENERATED_VERSION)
except ImportError:
    _version_not_supported = True

if _version_not_supported:
    raise RuntimeError(
        f'The grpc package installed is at version {GRPC_VERSION},'
        + f' but the generated code in chroma_pb2_grpc.py depends on'
        + f' grpcio>={GRPC_GENERATED_VERSION}.'
        + f' Please upgrade your grpc module to grpcio>={GRPC_GENERATED_VERSION}'
        + f' or downgrade your generated code using grpcio-tools<={GRPC_VERSION}.'
    )


class ChromaServiceStub(object):
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.AddDocument = channel.unary_unary(
                '/chroma.ChromaService/AddDocument',
                request_serializer=chroma__pb2.AddDocumentRequest.SerializeToString,
                response_deserializer=chroma__pb2.AddDocumentResponse.FromString,
                _registered_method=True)
        self.Query = channel.unary_unary(
                '/chroma.ChromaService/Query',
                request_serializer=chroma__pb2.QueryRequest.SerializeToString,
                response_deserializer=chroma__pb2.QueryResponse.FromString,
                _registered_method=True)


class ChromaServiceServicer(object):
    """Missing associated documentation comment in .proto file."""

    def AddDocument(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def Query(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_ChromaServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'AddDocument': grpc.unary_unary_rpc_method_handler(
                    servicer.AddDocument,
                    request_deserializer=chroma__pb2.AddDocumentRequest.FromString,
                    response_serializer=chroma__pb2.AddDocumentResponse.SerializeToString,
            ),
            'Query': grpc.unary_unary_rpc_method_handler(
                    servicer.Query,
                    request_deserializer=chroma__pb2.QueryRequest.FromString,
                    response_serializer=chroma__pb2.QueryResponse.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'chroma.ChromaService', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers('chroma.ChromaService', rpc_method_handlers)


 # This class is part of an EXPERIMENTAL API.
class ChromaService(object):
    """Missing associated documentation comment in .proto file."""

    @staticmethod
    def AddDocument(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/chroma.ChromaService/AddDocument',
            chroma__pb2.AddDocumentRequest.SerializeToString,
            chroma__pb2.AddDocumentResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def Query(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/chroma.ChromaService/Query',
            chroma__pb2.QueryRequest.SerializeToString,
            chroma__pb2.QueryResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)
