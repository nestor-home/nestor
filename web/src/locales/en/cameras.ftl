## Watching and calling through satellites, pictures on demand.

cam-off-reason = { $off ->
    [quiet_hours] off during quiet hours
    [someone_home] off while someone is home
   *[switched_off] camera switched off
}
cam-view = View
cam-view-for = View { $name }
cam-call = Call
cam-call-for = Call through { $name }
cam-picture = Picture
cam-picture-for = Take a picture with { $name }
cam-view-title = { $name }, live
cam-call-title = Call through { $name }
cam-picture-title = Picture from { $name }
cam-picture-alt = What { $name } films in “{ $room }”
cam-picture-again = Take another
cam-taking = Taking the picture…
cam-download = Download
cam-stream = What { $name } sends
cam-connecting = Connecting…
cam-audio-only = No picture: you hear “{ $room }” and it hears you.
cam-ended = The session ended.
cam-left = { $remaining } left
cam-mute = Mute
cam-unmute = Unmute
cam-hang-up = Hang up
cam-again = Try again
cam-unsupported = This browser cannot receive video. Use a recent Chrome, Firefox or Safari.
cam-failed = The connection could not be set up.
cam-view-note = What it films in “{ $room }”, until you close.
cam-call-note = “{ $room }” hears you until you hang up.
