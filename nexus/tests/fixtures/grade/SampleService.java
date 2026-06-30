public class SampleService {
    public void kick(CrewData actor) {
        if (actor.isBelowGrade(GradeType.MANAGER)) throw new RuntimeException("nope");
    }

    public void join(CrewData actor) {
        // no grade gate — anyone can join
    }

    public void promote(CrewData actor, CrewData target, GradeType targetGrade) {
        if (targetGrade.isEqualOrHigherThan(actor.getGradeType())) throw new RuntimeException("nope");
    }

    public java.util.List<CrewData> managers(java.util.List<CrewData> crews) {
        return crews.stream()
            .filter(c -> c.isEqualOrHigherThan(GradeType.MANAGER))
            .toList();
    }
}
