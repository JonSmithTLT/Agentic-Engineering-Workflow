**A request file's name is unique and ordered within a process.** Two requests of one kind on one clock tick (about
15.6 ms on Windows before Python 3.13) once shared a name, so the second's file replaced the first's. In a Lead session
these commands run inside the long-lived broker process, so the pid does not separate them; a real collision needs two
same-kind requests on one run inside one tick, with a control-state commit between them. Outside a session each command
has its own process. A clock step back inside one broker session is the more reachable case, and the name holds its order
through it too. Across processes the limit stands, on one tick or across a clock step back: two requests sort by pid or by
the stepped clock, not by issue order. So after a step back, a stop from an own shell can sort before an earlier broker
send and end the run before it. Each request keeps its own file, so none is lost.
