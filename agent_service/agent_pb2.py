# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: agent.proto
# Protobuf Python Version: 4.25.1
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x0b\x61gent.proto\x12\x05\x61gent\"\"\n\x0c\x41gentRequest\x12\x12\n\nuser_query\x18\x01 \x01(\t\"I\n\nAgentReply\x12\x14\n\x0c\x66inal_answer\x18\x01 \x01(\t\x12\x14\n\x0c\x63ontext_used\x18\x02 \x01(\t\x12\x0f\n\x07sources\x18\x03 \x01(\t2D\n\x0c\x41gentService\x12\x34\n\nQueryAgent\x12\x13.agent.AgentRequest\x1a\x11.agent.AgentReplyb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'agent_pb2', _globals)
if _descriptor._USE_C_DESCRIPTORS == False:
  DESCRIPTOR._options = None
  _globals['_AGENTREQUEST']._serialized_start=22
  _globals['_AGENTREQUEST']._serialized_end=56
  _globals['_AGENTREPLY']._serialized_start=58
  _globals['_AGENTREPLY']._serialized_end=131
  _globals['_AGENTSERVICE']._serialized_start=133
  _globals['_AGENTSERVICE']._serialized_end=201
# @@protoc_insertion_point(module_scope)
