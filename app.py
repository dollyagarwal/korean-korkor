import os
from flask import Flask, render_template, request, jsonify, make_response
from base64 import b64encode
import json, requests, re
from kaldialign import align
from datetime import datetime
import librosa
import soundfile as sf
import subprocess
from compute_gop import compute_mispronounce

app = Flask(__name__)

app.config.from_object(os.environ['APP_SETTINGS'])
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
google_api_key = os.environ['GOOGLE_API_KEY']

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/record")
def record():
    return render_template("record.html")

@app.route("/upload", methods=['POST'])
def upload():
    wav_file = request.files['file']
    canonical = request.form['canonical'].strip()

    #################################
    ### GOOGLE SPEECH-TO-TEXT API ###
    #################################

    # Get pure hangeul
    cleaned_canonical = ""
    for char in canonical:
        if re.match("[\uac00-\ud7a3]", char):
            cleaned_canonical += char

    # For Google STT API
    base64_str = b64encode(wav_file.read()).decode('utf-8')
    url = 'https://speech.googleapis.com/v1p1beta1/speech:recognize?key=' + google_api_key
    json_body = {
        "audio": {
            "content": base64_str
        },
        "config": {
            "enableAutomaticPunctuation": False,
            "encoding": "LINEAR16",
            "languageCode": "ko-KR",
            "model": "default"
        }
    }

    res = requests.post(url, data=json.dumps(json_body))
    
    # Get the transcription with the highest confidence
    google_trans = res.json()['results'][0]['alternatives'][0]['transcript']
    google_conf = res.json()['results'][0]['alternatives'][0]['confidence']

    # Clean transcript
    cleaned_trans = ""
    for char in google_trans:
        if re.match("[\uac00-\ud7a3]", char):
            cleaned_trans += char

    google_matched_text = align(cleaned_canonical, cleaned_trans, "*")

    # Count the number of correct characters
    correct = 0
    for pair in google_matched_text:
        if pair[0] == pair[1]:
            correct += 1
    google_score = correct/len(google_matched_text)
    print('Google STT call successful')
    
    #################################
    ### KALDI BASED TRANSCRIPTION ###
    #################################

    # Create the AUDIO_INFO file in test_prod
    f = open("../kaldi/egs/zeroth_korean/s5/test_prod/AUDIO_INFO", "w")
    f.write("SPEAKERID|NAME|SEX|SCRIPTID|DATASET\n")
    f.write("117|EugeneTan|m|003|test_prod\n")
    f.close()
    print('Created audio info')
    
    # Create a directory containing the audio and the canonical text
    f = open("../kaldi/egs/zeroth_korean/s5/test_prod/new/003/117/117_003.trans.txt", "w")
    f.write("117_003_0008 " + canonical + "\n")
    f.close()
    print('Created canonical transcript')

    # Do the necessary conversion: 44.1kHz wav -> 16kHz flac
    wav_file.seek(0)  # Return the pointer to the beginning
    data, samplingrate = librosa.load(wav_file, sr=16000)  # Downsampling
    sf.write('../kaldi/egs/zeroth_korean/s5/test_prod/new/003/117/117_003_0008.flac', data, samplingrate, format='flac')  # Save FLAC in the right directory
    print('Created FLAC file')

    # Remove data/new
    os.system("rm -r /home/sadm/Desktop/kaldi/egs/zeroth_korean/s5/data/new")
    print('Removed data/new')

    # Execute run_test_audio_gmm.sh and extract test ivectors and then compute gop
    os.chdir("../kaldi/egs/zeroth_korean/s5")
    subprocess.call("./run_test_audio_gmm.sh")
    subprocess.call("./extract_test_ivectors_oneaudio.sh")
    subprocess.call("./d_run_gop_oneaudio.sh")
    os.chdir("../../../../korean-korkor")
    print('Done executing bash')

    # Read ROS, AR and PTR
    f = open("../kaldi/egs/zeroth_korean/s5/exp/tri4_new_align/rate_evaluation.txt", "r")
    arr = f.read().split("\n")
    stats = {}
    stats['ROS'] = float(arr[0][4:]) if arr[0][4:] != 'nan' else -1
    stats['AR'] = float(arr[1][3:]) if arr[1][3:] != 'nan' else -1
    stats['PTR'] = float(arr[2][4:]) if arr[2][4:] != 'nan' else -1
    f.close()

    # Read transcription
    f = open("../kaldi/egs/zeroth_korean/s5/exp/tri4/decode_tgsmall_new/one_best_transcription.txt", "r")
    arr = f.read()
    stats['transcription'] = arr[13:-1]  # Trim 13-letter code and ending line break
    f.close()

    # Get duration
    f = open("../kaldi/egs/zeroth_korean/s5/data/new/utt2dur", "r")
    arr = f.read()
    stats['duration'] = float(arr[13:-1])  # Similar format to transcription
    f.close()

    # Using kaldi results
    trans = stats['transcription']
    conf = 1  # Kaldi does not generate confidence

    # Clean transcript
    cleaned_trans = ""
    for char in trans:
        if re.match("[\uac00-\ud7a3]", char):
            cleaned_trans += char

    matched_text = align(cleaned_canonical, cleaned_trans, "*")

    # Count the number of correct characters
    correct = 0
    for pair in matched_text:
    	if pair[0] == pair[1]:
    		correct += 1
    score = correct/len(matched_text)

    # Calculate WPM and words correct per minute
    wpm = len(cleaned_trans)/(stats['duration']/60)
    wcpm = correct/(stats['duration']/60)

    # Map phone to corresponding GOP score
    gop_file = "../kaldi/egs/zeroth_korean/s5/exp/gop_new/gop.1.txt"
    pure_phone_file = "../kaldi/egs/zeroth_korean/s5/exp/gop_new/phones-pure.txt"
    phone_list, gop_list = compute_mispronounce(gop_file,pure_phone_file)

    # Generate phonemes from characters
    # os.chdir("../kaldi/egs/zeroth_korean/s5/KoG2P-master-cs4347")
    # subprocess.call(["python", "get_phonemes.py", "../test_prod/new/003/117/117_003.trans.txt", "../exp/tri4/decode_tgsmall_new/one_best_transcription.txt"])

    # canonical_phoneme = open("output1.txt", "r").read()
    # transcribed_phoneme = open("output2.txt", "r").read()

    os.chdir("../../../../../korean-korkor")
    # print('Done getting phonemes')

    # Match phonemes
    # matched_phonemes = align(canonical_phoneme.split(), transcribed_phoneme.split(), "*")

    to_return = {
        "google_transcription": google_trans,
        "google_confidence": google_conf,
        "google_matched_text": google_matched_text,
        "google_score": google_score,
        "transcription": trans,
        "confidence": conf,
        "matched_text": matched_text,
        "score": score,
        "ROS": stats["ROS"],
        "AR": stats["AR"],
        "PTR": stats["PTR"],
        "WPM": wpm,
        "WCPM": wcpm,
        "phones": phone_list,
        "gop": gop_list
     #   "matched_phonemes": matched_phonemes,
     #   "phoneme_transcription": transcribed_phoneme
    }
    print(to_return)

    # Save file in database for analysis purpose
    filename = datetime.today().strftime('%Y-%m-%d_%H:%M:%S')
    with open('audio/' + filename + '.wav', 'wb') as audio:
        wav_file.save(audio)
    print('Saved audio file')
    
    return make_response(jsonify(to_return), 200)
    
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=80)
