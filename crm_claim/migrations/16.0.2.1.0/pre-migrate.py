import json

from odoo.upgrade import util


def migrate(cr, version):
    cr.execute(
        """
            SELECT res_id
              FROM ir_model_data d
             WHERE NOT EXISTS (SELECT 1
                                 FROM ir_model_data
                                WHERE id != d.id
                                  AND res_id = d.res_id
                                  AND model = d.model
                                  AND module != d.module)
               AND module = 'crm_claim'
               AND model = 'ir.ui.view'
          ORDER BY id DESC
            """
    )
    for view_id in cr.fetchall():
        util.remove_view(cr, view_id=view_id)

    cr.execute(
        """
            SELECT res_id
              FROM ir_model_data d
             WHERE NOT EXISTS (SELECT 1
                                 FROM ir_model_data
                                WHERE id != d.id
                                  AND res_id = d.res_id
                                  AND model = d.model
                                  AND module != d.module)
               AND module = 'crm_claim'
               AND model = 'ir.ui.menu'
          ORDER BY id DESC
    """
    )
    menu_ids = cr.fetchall()
    util.remove_menus(cr, menu_ids)

    # crm_claim to helpdesk_ticket
    util.create_column(cr, "helpdesk_stage", "_stage_id", "int4")

    cr.execute(
        """
               INSERT INTO helpdesk_stage
                (_stage_id, name, sequence, legend_blocked, legend_normal, legend_done)
                SELECT id, name, sequence, '{ "de_DE": "Blockiert", "en_EN": "Blocked" }', '{ "de_DE": "In Bearbeitung", "en_EN": "In Progress" }', '{ "de_DE": "Erledigt", "en_EN": "Done" }'
               FROM crm_claim_stage
               WHERE NOT name ->> 'en_US' in ('New', 'Erledigt')
               """
    )

    cr.execute(
        """
        UPDATE helpdesk_stage SET
        (_stage_id) = (SELECT id FROM crm_claim_stage WHERE name ->> 'en_US' = 'New')
        WHERE name ->> 'en_US' = 'New'
        """
    )

    cr.execute(
        """
        UPDATE helpdesk_stage SET
        (_stage_id) = (SELECT id FROM crm_claim_stage WHERE name ->> 'en_US' = 'Erledigt')
        WHERE name ->> 'en_US' = 'Solved'
        """
    )

    util.create_column(cr, "helpdesk_ticket_type", "_categ_id", "int4")

    cr.execute(
        """
               INSERT INTO helpdesk_ticket_type
                (_categ_id, name)
               SELECT id, name
               FROM crm_claim_category
        """
    )

    util.create_column(cr, "helpdesk_ticket", "_claim_id", "int4")
    util.create_column(cr, "helpdesk_ticket", "_categ_id", "int4")
    util.create_column(cr, "helpdesk_ticket", "_stage_id", "int4")

    cr.execute(
        """
               INSERT INTO helpdesk_ticket
               (_claim_id, _categ_id, _stage_id, ticket_ref, name, active, sale_order_id, create_date, write_date, close_date, description, partner_id, user_id, company_id, kanban_state)
               SELECT
               id, categ_id, stage_id, nextval('helpdesk_ticket_id_seq'), name, active, CAST(split_part(model_ref_id, ',', 2) AS INTEGER) as sale_order_id, create_date, write_date, date_closed, description, partner_id, user_id, company_id, 'normal'
               FROM crm_claim WHERE model_ref_id like 'sale.order,%' and exists(select 1 from sale_order where id = cast(split_part(model_ref_id, ',', 2) as integer))
        """
    )

    cr.execute(
        """
           WITH temp_table AS (
               SELECT id, _claim_id FROM helpdesk_ticket WHERE _claim_id IS NOT NULL
           )
           UPDATE mail_message SET
               model = 'helpdesk.ticket',
               res_id = temp_table.id
           FROM temp_table
           WHERE mail_message.model = 'crm.claim'
           AND mail_message.res_id = temp_table._claim_id
        """
    )

    cr.execute(
        """
           UPDATE mail_followers SET
               res_model = 'helpdesk.ticket',
               res_id = helpdesk_ticket.id
           FROM helpdesk_ticket
           WHERE mail_followers.res_model = 'crm.claim'
           AND mail_followers.res_id = helpdesk_ticket._claim_id
        """
    )

    cr.execute(
        """
           WITH temp_table AS (
               SELECT id, _claim_id FROM helpdesk_ticket WHERE _claim_id IS NOT NULL
           )
           UPDATE ir_attachment SET
               res_model = 'helpdesk.ticket',
               res_id = temp_table.id
           FROM temp_table
           WHERE ir_attachment.res_model = 'crm.claim'
           AND ir_attachment.res_id = temp_table._claim_id
        """
    )

    util.merge_model(cr, "crm.claim.stage", "helpdesk.stage")
    util.merge_model(cr, "crm.claim.category", "helpdesk.ticket.type")

    cr.execute(
        """
           UPDATE helpdesk_ticket SET
            ticket_type_id = htt.id
           FROM helpdesk_ticket_type htt
           WHERE htt._categ_id = helpdesk_ticket._categ_id
        """
    )

    cr.execute(
        """
           UPDATE helpdesk_ticket SET
            stage_id = hs.id
           FROM helpdesk_stage hs
           WHERE hs._stage_id = helpdesk_ticket._stage_id
        """
    )

    cr.execute(
        "SELECT id FROM res_company WHERE NOT EXISTS (SELECT 1 FROM helpdesk_team ht WHERE ht.company_id = res_company.id)"
    )

    cr.execute("SELECT id from ir_model WHERE model = 'helpdesk.ticket'")
    helpdesk_ticket_model_id = cr.fetchone()[0]

    cr.execute("SELECT id from ir_model WHERE model = 'helpdesk.team'")
    helpdesk_team_model_id = cr.fetchone()[0]

    cr.execute(
        "SELECT id, name from res_company WHERE id != 26 AND NOT EXISTS (SELECT 1 FROM helpdesk_team ht WHERE ht.company_id = res_company.id)"
    )
    missing_teams_company_ids = cr.fetchall()

    for missing_team_company_id, company_name in missing_teams_company_ids:
        cr.execute(
            """
            WITH alias_key AS (
                INSERT INTO mail_alias (alias_name, alias_model_id, alias_user_id, alias_defaults, alias_parent_model_id, alias_parent_thread_id, alias_contact)
                SELECT %s, %s, 1, to_json('{}'::text), %s, 1, 'everyone'
                RETURNING id
                )
            INSERT INTO helpdesk_team
                   (name, alias_id,
                    active, company_id, sequence, color,
                    assign_method, use_alias, allow_portal_ticket_closing, use_website_helpdesk_form, use_website_helpdesk_livechat,
                    use_website_helpdesk_forum, use_website_helpdesk_slides, use_helpdesk_timesheet, use_helpdesk_sale_timesheet, use_credit_notes,
                    use_coupons, use_product_returns, use_product_repairs, use_twitter, use_rating,
                    portal_show_rating, use_sla, auto_close_ticket, auto_close_day, to_stage_id,
                    use_fsm, privacy_visibility, auto_assignment, use_website_helpdesk_knowledge)
               SELECT
                   %s,
                   alias_key.id,
                   true, res_company.id, 10, 0,
                   'randomly', true, false, false, false,
                   false, false, false, false, false,
                   false, false, false, false, false,
                   false, false, false, 7, 3,
                   false, 'internal', false, false
               FROM alias_key, res_company WHERE res_company.id = %s
               RETURNING id, alias_id
               """,
            (
                "support-%s" % str(company_name).split(" ")[0].lower(),
                helpdesk_ticket_model_id,
                helpdesk_team_model_id,
                json.dumps(
                    {
                        "de_DE": "Support %s" % company_name,
                        "en_US": "Support %s" % company_name,
                    }
                ),
                missing_team_company_id,
            ),
        )
        team_id, alias_id = cr.fetchone()
        cr.execute(
            "UPDATE mail_alias SET alias_defaults = to_json('{\"team_id\": %s}'::text) WHERE id = %s",
            (team_id, alias_id),
        )

    cr.execute(
        """
            SELECT id, _claim_id FROM helpdesk_ticket WHERE _claim_id IS NOT NULL
        """
    )
    ticket_claim_tuples = cr.fetchall()
    mapping = {ticket_id: claim_id for ticket_id, claim_id in ticket_claim_tuples}
    util.replace_record_references_batch(cr, mapping, "helpdesk.ticket", "crm.claim")

    cr.execute(
        """
            UPDATE helpdesk_ticket AS ht SET company_id = rp.company_id FROM res_partner AS rp WHERE rp.id = ht.partner_id
        """
    )

    cr.execute(
        """
            UPDATE helpdesk_ticket AS ht SET team_id = team.id FROM helpdesk_team AS team WHERE ht.company_id = team.company_id
        """
    )

    cr.execute(
        """
           UPDATE mail_message SET
               model = 'helpdesk.ticket',
               res_id = ht.id
           FROM helpdesk_ticket ht
           WHERE mail_message.model = 'crm.claim'
           AND mail_message.res_id = ht._claim_id
        """
    )

    cr.execute(
        """
           UPDATE ir_attachment SET
               res_model = 'helpdesk.ticket',
               res_id = ht.id
           FROM helpdesk_ticket ht
           WHERE ir_attachment.res_model = 'crm.claim'
           AND ir_attachment.res_id = ht._claim_id
        """
    )

    util.merge_model(cr, "crm.claim", "helpdesk.ticket")
    util.remove_column(cr, "helpdesk_stage", "_stage_id")
    util.remove_column(cr, "helpdesk_ticket_type", "_categ_id")
    util.remove_column(cr, "helpdesk_ticket", "_stage_id")
    util.remove_column(cr, "helpdesk_ticket", "_categ_id")
    util.remove_column(cr, "helpdesk_ticket", "_claim_id")
