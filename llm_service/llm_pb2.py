# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: llm.proto
# Protobuf Python Version: 5.29.0
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    5,
    29,
    0,
    '',
    'llm.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\tllm.proto\x12\x03llm\"J\n\x0fGenerateRequest\x12\x0e\n\x06prompt\x18\x01 \x01(\t\x12\x12\n\nmax_tokens\x18\x02 \x01(\x05\x12\x13\n\x0btemperature\x18\x03 \x01(\x02\"3\n\x10GenerateResponse\x12\r\n\x05token\x18\x01 \x01(\t\x12\x10\n\x08is_final\x18\x02 \x01(\x08\x32G\n\nLLMService\x12\x39\n\x08Generate\x12\x14.llm.GenerateRequest\x1a\x15.llm.GenerateResponse0\x01\x62\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'llm_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_GENERATEREQUEST']._serialized_start=18
  _globals['_GENERATEREQUEST']._serialized_end=92
  _globals['_GENERATERESPONSE']._serialized_start=94
  _globals['_GENERATERESPONSE']._serialized_end=145
  _globals['_LLMSERVICE']._serialized_start=147
  _globals['_LLMSERVICE']._serialized_end=218
# @@protoc_insertion_point(module_scope)
