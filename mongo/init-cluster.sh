#!/usr/bin/env bash
set -e
docker exec configsvr mongosh --quiet --eval \
  "rs.initiate({_id:'cfgrs', configsvr:true, members:[{_id:0, host:'configsvr:27017'}]})"
docker exec shard1 mongosh --quiet --eval \
  "rs.initiate({_id:'shard1rs', members:[{_id:0, host:'shard1:27017'}]})"
docker exec shard2 mongosh --quiet --eval \
  "rs.initiate({_id:'shard2rs', members:[{_id:0, host:'shard2:27017'}]})"
echo 'Waiting for replica sets to elect primaries...'; sleep 20
docker exec mongos mongosh --quiet --eval \
  "sh.addShard('shard1rs/shard1:27017'); sh.addShard('shard2rs/shard2:27017'); sh.status()"
