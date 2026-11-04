import json, random, sys
n_tests, per = int(sys.argv[1]), int(sys.argv[2]); out = sys.argv[3]
random.seed(7)
mods = {"STR":("EST.nwc","Structural Framing","Concrete-Rectangular Beam"),"ARC":("ARQ.nwc","Walls","Basic Wall"),
        "HVAC":("MEC.nwc","Ducts","Rectangular Duct"),"PLB":("HID.nwc","Pipes","Pipe Types"),
        "ELE":("ELE.nwc","Cable Trays","Cable Tray"),"FIRE":("RCI.nwc","Pipes","Pipe Types")}
codes=list(mods); pairs=[(a,b) for i,a in enumerate(codes) for b in codes[i+1:]]
tests=[]; clashes=[]; k=0
for t in range(n_tests):
    a,b = pairs[t%len(pairs)]; name=f"T{t:03d} {a}-{b}"
    tests.append({"name":name,"kind":"hard","status":"active","tolerance":0.0,"count":per})
    for i in range(per):
        k+=1; lv=random.randint(1,12); x=random.uniform(0,400); y=random.uniform(0,200); z=lv*3.5
        def el(c,j):
            m,cat,fam=mods[c]; bb=[[x-1,y-1,z],[x+1,y+1,z+0.4]]
            return {"id":f"{m}:{c}{random.randint(1,40000)}","name":f"{fam} {j}","category":cat,"family":fam,"model":m,"level":f'Level "L{lv}", #{9000+lv}',"props":{"Id":str(k)},"bbox":bb}
        clashes.append({"id":f"c{k}","test":name,"name":f"Clash{k}","status":"new","kind":"hard","distance":-random.uniform(0.005,0.3),"point":[x,y,z],"a":el(a,i),"b":el(b,i),"level":f'Level "L{lv}", #{9000+lv}'})
json.dump({"schema":"vdc_navis_lab.clashset/1","source":"stress","document":{"title":"STRESS.nwf","fingerprint":"stress"},"models":[v[0] for v in mods.values()],"truncated":False,"tests":tests,"clashes":clashes},open(out,"w"))
print(out,len(clashes))
