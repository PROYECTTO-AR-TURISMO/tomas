import pyttsx3, threading, queue, time
q = queue.Queue()
def run():
 while True:
  t = q.get()
  e = pyttsx3.init()
  e.say(t)
  e.runAndWait()
  del e

threading.Thread(target=run, daemon=True).start()
q.put('Uno')
time.sleep(2)
q.put('Dos')
time.sleep(2)
q.put('Tres')
time.sleep(3)
