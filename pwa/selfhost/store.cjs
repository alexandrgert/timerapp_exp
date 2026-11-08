'use strict';
const {DatabaseSync,backup}=require('node:sqlite');
const {createHash,randomBytes,randomUUID}=require('node:crypto');
const fs=require('node:fs'),path=require('node:path');
const hash=value=>createHash('sha256').update(value).digest('hex');
function openStore(root){
 if(!root||!path.isAbsolute(root))throw Error('CLOUDCLI_DATA_DIR must be an absolute persistent directory');
 fs.mkdirSync(root,{recursive:true,mode:0o700});
 const filename=path.join(root,'tasktimer.sqlite');
 const db=new DatabaseSync(filename);fs.chmodSync(filename,0o600);
 db.exec('PRAGMA busy_timeout=5000; PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;');
 try{
 db.exec('BEGIN IMMEDIATE');
 const version=db.prepare('PRAGMA user_version').get().user_version;
 if(version>1)throw Error('Unsupported database version; use matching server release');
 if(version===0){
 if(db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all().length)throw Error('Unrecognized database schema; refusing initialization');
 db.exec(`CREATE TABLE devices(id TEXT PRIMARY KEY,label TEXT NOT NULL,digest TEXT UNIQUE NOT NULL,created TEXT NOT NULL,revoked INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL,etag TEXT NOT NULL);
 PRAGMA user_version=1;`);
 }else{
 // A damaged existing schema must fail, never recreate an empty dataset.
 db.prepare('SELECT id,label,digest,created,revoked FROM devices LIMIT 0').all();
 db.prepare('SELECT id,body,etag FROM state LIMIT 0').all();
 }
 db.exec('COMMIT');
 }catch(error){try{db.exec('ROLLBACK');}finally{db.close();}throw error;}

 return {
 addDevice(label){if(typeof label!=='string'||!label.trim()||label.length>100)throw Error('Device label required (1–100 characters)');const token=randomBytes(32).toString('base64url'),id=randomUUID();db.prepare('INSERT INTO devices(id,label,digest,created) VALUES(?,?,?,?)').run(id,label,hash(token),new Date().toISOString());return {id,token};},
 devices(){return db.prepare('SELECT id,label,created,revoked FROM devices ORDER BY created').all();},
 revoke(id){return Number(db.prepare('UPDATE devices SET revoked=1 WHERE id=? AND revoked=0').run(id).changes);},
 authorized(token){return typeof token==='string'&&/^[A-Za-z0-9_-]{43}$/.test(token)&&!!db.prepare('SELECT id FROM devices WHERE digest=? AND revoked=0').get(hash(token));},
 read(){return db.prepare('SELECT body,etag FROM state WHERE id=1').get()||null;},
 write(body,{etag,create}){
 db.exec('BEGIN IMMEDIATE');try{const current=this.read();if(create?!!current:(!current||current.etag!==etag)){db.exec('ROLLBACK');return false;}const next='"'+hash(body)+'"';db.prepare('INSERT INTO state(id,body,etag) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,etag=excluded.etag').run(body,next);db.exec('COMMIT');return next;}catch(e){db.exec('ROLLBACK');throw e;}
 },
 async backup(destination){if(!path.isAbsolute(destination)||fs.existsSync(destination))throw Error('Backup must be a new absolute file');await backup(db,destination);fs.chmodSync(destination,0o600);},
 close(){db.close();}
 };
}
module.exports={openStore};
