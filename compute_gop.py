import os

def compute_mispronounce(file,pure_phone_file):

    phone_dict = {}
    ## make dictionary of phone and int mapping
    with open(pure_phone_file,'r',encoding='utf-8') as sf:
        lines = sf.readlines()
        for line in lines:
            l = line.split('\t')
            phone_dict[l[1].strip()]=l[0].strip()

    #print(phone_dict)
    ## find phone list and gop list
    with open(file,'r',encoding='utf-8') as f:
        lines = f.readlines()

        for line in lines:
            #print(line)
            values = line.split('[')
            utt = values[0].strip()
            phone_list = []
            gop_list = []
            phone_name_list = []
            #print('For Utterance: ', utt)
            values = [s.replace(']','') for s in values]
            for i in range(1,len(values)):
                val = values[i].strip().split(' ')
                phone_list.append(val[0])
                gop_list.append(val[1])
                phone_name_list.append(phone_dict[val[0]])
                #if float(val[1])<-5.:
                    #print(val[0],':',phone_dict[val[0]])
            #print(phone_list)
            #print(gop_list)
            #print(phone_name_list)
            return phone_name_list,gop_list