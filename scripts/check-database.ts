import { prisma } from "../prisma/client";

try {
  const [users, incidents, remediationPlans, auditRecords, platformRecords, archivedAuditRecords] = await Promise.all([
    prisma.user.count(), prisma.incident.count(), prisma.remediationPlan.count(),
    prisma.auditLog.count(), prisma.platformRecord.count(),
    prisma.platformRecord.count({ where: { key: { startsWith: "legacy-audit:" } } }),
  ]);
  console.log(JSON.stringify({ connected: true, users, incidents, remediationPlans, auditRecords, archivedAuditRecords, platformRecords }, null, 2));
} finally {
  await prisma.$disconnect();
}
