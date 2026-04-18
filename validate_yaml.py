import yamale
schema = yamale.make_schema('schema.yaml')
data = yamale.make_data('npc_engine/config/world/nodes/regions/ancient_temple.yaml')
yamale.validate(schema, data)   
